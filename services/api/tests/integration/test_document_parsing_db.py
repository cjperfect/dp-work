"""验证解析任务的权限、幂等、租约恢复及过期结果隔离。"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge import parsing, storage
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from app.modules.users.models import User
from app.modules.users import service as users_service


def test_pdf_parse_persistence_ownership_retry_and_stale_result(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    rpc = AsyncMock(return_value={"status": "parsed", "content": "# PDF contents\n\n|Name|Value|\n|---|---|\n|A|42|", "metadata": [{"page_number": 1}]})
    monkeypatch.setattr(parsing, "sidecar", rpc)
    async def case():
        await session.init_db()
        owners, bases = [], []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user("parse-" + uuid4().hex, "test", "product"))
            async with session.transaction() as db:
                for owner in owners:
                    base = KnowledgeBase(owner_id=owner.id, name="解析测试")
                    db.add(base)
                    bases.append(base)
                await db.flush()
            headers = [{"Authorization": "Bearer " + create_access_token(owner.id, owner.role, owner.department)} for owner in owners]
            url = f"/api/knowledge-bases/{bases[0].id}/documents"
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                doc = (await client.post(url + "/upload", headers=headers[0], files={"file": ("sample.pdf", b"%PDF-1.4\nfixture")})).json()["data"]
                path = url + "/" + doc["id"]
                assert (await client.post(path + "/parse")).status_code == 401
                assert (await client.post(path + "/parse", headers=headers[1])).status_code == 404
                for _ in range(2):
                    response = await client.post(path + "/parse", headers=headers[0])
                    assert response.status_code == 200, response.text
                    assert response.json()["data"]["parse_status"] == "queued"
                row = await parsing.claim()
                assert row.id == doc["id"]
                assert await parsing.claim() is None
                # 数据库重连后，过期租约仍可重新领取；旧 worker 不得覆盖新租约。
                await session.close_db()
                await session.init_db()
                async with session.transaction() as db:
                    await db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id == row.id).values(parse_lease_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
                recovered = await parsing.claim()
                assert recovered.parse_claim_token != row.parse_claim_token
                assert not await parsing.finish(row, parse_status="parsed", parse_content="stale")
                await parsing.process(recovered)
                saved = (await client.get(path, headers=headers[0])).json()["data"]
                assert saved["parse_status"] == "parsed" and "42" in saved["parse_content"]
                assert saved["content"] == "" and saved["parsed_at"]
                assert "storage_key" not in saved and "parse_claim_token" not in saved
                assert rpc.await_count == 1
                assert (await client.post(path + "/parse", headers=headers[0])).json()["data"]["parse_status"] == "parsed"
                # 显式失败可重试。
                async with session.transaction() as db:
                    await db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id == row.id).values(parse_status="failed", parse_error="old"))
                assert (await client.post(path + "/parse", headers=headers[0])).json()["data"]["parse_error"] is None
                rpc.side_effect = ValueError("PDF 未提取到文字")
                await parsing.process(await parsing.claim())
                failed = (await client.get(path, headers=headers[0])).json()["data"]
                assert failed["parse_status"] == "failed" and "文字" in failed["parse_error"]
                # 删除后的任务结果不能复活文档。
                await client.post(path + "/parse", headers=headers[0])
                row = await parsing.claim()
                await client.delete(path, headers=headers[0])
                assert not await parsing.finish(row, parse_status="parsed", parse_content="deleted")
                # 文本格式可提交解析，Word 仍明确拒绝。
                for name, body in [("a.txt", b"text"), ("a.markdown", b"# text"), ("a.doc", bytes.fromhex("d0cf11e0a1b11ae1")), ("a.docx", b"PK\x03\x04fixture")]:
                    response = await client.post(url + "/upload", headers=headers[0], files={"file": (name, body)})
                    assert response.status_code == 200, response.text
                    item_path = url + "/" + response.json()["data"]["id"]
                    assert (await client.get(item_path + "/file", headers=headers[0])).content == body
                    assert (await client.post(item_path + "/parse", headers=headers[0])).status_code == (400 if name.endswith(".doc") else 200)
                    if name.endswith((".txt", ".markdown", ".docx")):
                        rpc.side_effect = None
                        await parsing.process(await parsing.claim())
                # 修改正文清空旧解析结果，重复保存相同正文则保持。
                editor = url + "/editor-" + uuid4().hex
                body = {"title": "note", "content": "original", "blocks": None}
                saved = (await client.put(editor, headers=headers[0], json=body)).json()["data"]
                async with session.transaction() as db:
                    await db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id == saved["id"]).values(parse_status="parsed", parse_content="old"))
                same = (await client.put(editor, headers=headers[0], json=body)).json()["data"]
                assert same["parse_status"] == "parsed"
                body["content"] = "changed"
                changed = (await client.put(editor, headers=headers[0], json=body)).json()["data"]
                assert changed["parse_status"] == "unparsed" and changed["parse_content"] is None
        finally:
            async with session.transaction() as db:
                ids = [base.id for base in bases]
                await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id.in_(ids)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
