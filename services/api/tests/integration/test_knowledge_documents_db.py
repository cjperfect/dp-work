"""验证在线文档持久化、幂等更新及账号隔离。"""
import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, func

from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from app.modules.users.models import User
from app.modules.users import service as users_service


def test_document_autosave_survives_reconnection_and_respects_ownership():
    async def case():
        await session.init_db()
        owners = []
        bases = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"docs-{uuid4().hex}", "test", "product"))
            async with session.transaction() as db:
                for owner in owners:
                    base = KnowledgeBase(owner_id=owner.id, name="文档库", description="")
                    db.add(base)
                    bases.append(base)
                await db.flush()
            headers = [{"Authorization": f"Bearer {create_access_token(owner.id, owner.role, owner.department)}"} for owner in owners]
            document_id = f"editor-{uuid4()}"
            path = f"/api/knowledge-bases/{bases[0].id}/documents/{document_id}"
            blocks = [{"id": "paragraph", "type": "paragraph", "content": [{"type": "text", "text": "正文🙂", "styles": {"bold": True}}]}]
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                assert (await client.put(path, json={})).status_code == 401
                response = await client.put(path, headers=headers[0], json={})
                assert response.status_code == 200, response.text
                assert response.json()["data"]["title"] == "未命名文档"
                created_at = response.json()["data"]["created_at"]
                content = {"title": " 项目说明 ", "content": "**正文🙂**\n", "blocks": blocks}
                for _ in range(2):
                    saved = await client.put(path, headers=headers[0], json=content)
                    assert saved.status_code == 200, saved.text
                    assert saved.json()["data"]["id"] == document_id
                async with session.read_session() as db:
                    assert await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.id == document_id)) == 1
                await session.close_db()
                await session.init_db()
                restored = (await client.get(path, headers=headers[0])).json()["data"]
                assert restored["title"] == "项目说明"
                assert restored["content"] == content["content"]
                assert restored["blocks"] == blocks
                assert restored["created_at"] == created_at
                listed = await client.get(f"/api/knowledge-bases/{bases[0].id}/documents", headers=headers[0])
                assert [item["id"] for item in listed.json()["data"]] == [document_id]
                bases_page = (await client.get("/api/knowledge-bases", headers=headers[0])).json()["data"]
                assert next(row for row in bases_page["item"] if row["id"] == bases[0].id)["document_count"] == 1
                for method in ("get", "put", "delete"):
                    kwargs = {"json": content} if method == "put" else {}
                    assert (await getattr(client, method)(path, headers=headers[1], **kwargs)).status_code == 404
                # 同 ID 不能通过另一个知识库覆盖。
                other_path = f"/api/knowledge-bases/{bases[1].id}/documents/{document_id}"
                assert (await client.put(other_path, headers=headers[1], json=content)).status_code == 404
                assert (await client.delete(other_path, headers=headers[1])).status_code == 404
                assert (await client.delete(f"/api/knowledge-bases/{bases[0].id}", headers=headers[1])).status_code == 404
                assert (await client.get(path, headers=headers[0])).status_code == 200
                assert (await client.delete(path, headers=headers[0])).status_code == 200
                assert (await client.get(path, headers=headers[0])).status_code == 404
                assert (await client.delete(path, headers=headers[0])).status_code == 404
                assert (await client.get(f"/api/knowledge-bases/{bases[0].id}/documents", headers=headers[0])).json()["data"] == []
                assert (await client.put(path, headers=headers[0], json=content)).status_code == 200
                assert (await client.delete(f"/api/knowledge-bases/{bases[0].id}", headers=headers[0])).status_code == 200
                assert (await client.get(path, headers=headers[0])).status_code == 404
                async with session.read_session() as db:
                    assert await db.get(KnowledgeDocument, document_id) is None
        finally:
            async with session.transaction() as db:
                ids = [base.id for base in bases]
                await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id.in_(ids)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
