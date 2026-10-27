"""验证文件落盘、列表、源文件读取、权限与失败清理。"""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.knowledge import storage
from src.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from src.modules.knowledge.repository import KnowledgeRepository
from src.modules.users.models import User
from src.modules.users import service as users_service


def test_upload_list_preview_deletion_and_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    async def case():
        await session.init_db()
        owners, bases = [], []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"uploads-{uuid4().hex}", "test", "product"))
            async with session.transaction() as db:
                for owner in owners:
                    base = KnowledgeBase(owner_id=owner.id, name="上传资料", description="")
                    db.add(base)
                    bases.append(base)
                await db.flush()
            headers = [{"Authorization": f"Bearer {create_access_token(owner.id, owner.role, owner.department)}"} for owner in owners]
            base_url = f"/api/knowledge-bases/{bases[0].id}/documents"
            async with AsyncClient(transport=ASGITransport(app=create_app(), raise_app_exceptions=False), base_url="http://test") as client:
                markdown = "# 产品规范\n\n文件上传与向量化🙂\n".encode()
                assert (await client.post(base_url + "/upload", files={"file": ("资料.md", markdown)})).status_code == 401
                assert (await client.post(base_url + "/upload", headers=headers[1], files={"file": ("资料.md", markdown)})).status_code == 404
                response = await client.post(base_url + "/upload", headers=headers[0], files={"file": ("../产品规范.MD", markdown, "text/markdown")})
                assert response.status_code == 200, response.text
                doc = response.json()["data"]
                assert doc["source"] == "upload" and doc["file_type"] == "md"
                assert doc["original_name"] == "产品规范.MD"
                assert doc["content"] == markdown.decode()
                assert doc["byte_size"] == len(markdown)
                assert "storage_key" not in doc
                file_url = f"{base_url}/{doc['id']}/file"
                async with session.read_session() as db:
                    record = await db.get(KnowledgeDocument, doc["id"])
                    path = storage.file_path(record.storage_key)
                    assert path.is_relative_to(storage.DATA_DIR)
                    assert path.read_bytes() == markdown
                await session.close_db()
                await session.init_db()
                assert (await client.get(base_url, headers=headers[0])).json()["data"][0]["id"] == doc["id"]
                assert (await client.get(file_url, headers=headers[0])).content == markdown
                assert (await client.get(file_url, headers=headers[1])).status_code == 404
                assert (await client.get(file_url)).status_code == 401
                # 富文本接口不能覆盖上传的源文件。
                assert (await client.put(f"{base_url}/{doc['id']}", headers=headers[0], json={"content": "覆盖"})).status_code == 404
                assert (await client.delete(f"{base_url}/{doc['id']}", headers=headers[1])).status_code == 404
                assert path.exists()
                assert (await client.delete(f"{base_url}/{doc['id']}", headers=headers[0])).status_code == 200
                assert not path.exists()
                # 格式、编码与大小校验均不留下文档或文件。
                invalid = [("evil.exe", b"binary"), ("wrong.pdf", b"not a PDF"), ("empty.md", b""), ("encoding.md", b"\xff\xfe")]
                for name, body in invalid:
                    failed = await client.post(base_url + "/upload", headers=headers[0], files={"file": (name, body)})
                    assert failed.status_code == 400, failed.text
                with monkeypatch.context() as local:
                    local.setattr(storage, "MAX_FILE_SIZE", 8)
                    too_large = await client.post(base_url + "/upload", headers=headers[0], files={"file": ("large.md", b"x" * 9)})
                    assert too_large.status_code == 413
                with monkeypatch.context() as local:
                    local.setattr(KnowledgeRepository, "create_upload", AsyncMock(side_effect=RuntimeError("db failure")))
                    failed = await client.post(base_url + "/upload", headers=headers[0], files={"file": ("rollback.md", markdown)})
                    assert failed.status_code == 500
                assert not list((storage.DATA_DIR / "knowledge").rglob("*.*"))
                assert not list((storage.DATA_DIR.parent / "temp/uploads").iterdir())
                assert (await client.get(base_url, headers=headers[0])).json()["data"] == []
                # 同名不覆盖；PDF 原始字节可读取，知识库删除后统一清理。
                pdf = b"%PDF-1.4\nfixture PDF bytes\n%%EOF"
                first = await client.post(base_url + "/upload", headers=headers[0], files={"file": ("资料.pdf", pdf, "application/pdf")})
                second = await client.post(base_url + "/upload", headers=headers[0], files={"file": ("资料.pdf", pdf, "application/pdf")})
                assert first.status_code == second.status_code == 200
                assert first.json()["data"]["id"] != second.json()["data"]["id"]
                pdf_url = f"{base_url}/{first.json()['data']['id']}/file"
                downloaded = await client.get(pdf_url, headers=headers[0])
                assert downloaded.content == pdf and downloaded.headers["content-type"] == "application/pdf"
                await client.delete(f"/api/knowledge-bases/{bases[0].id}", headers=headers[0])
                assert not list((storage.DATA_DIR / "knowledge").rglob("*.*"))
        finally:
            async with session.transaction() as db:
                base_ids = [base.id for base in bases]
                await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id.in_(base_ids)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(base_ids)))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
