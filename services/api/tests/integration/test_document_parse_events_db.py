"""文档解析通知只推送给所有者，并覆盖完成、重连和人工修改。"""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import delete, select

from app.core import config
from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge import parsing, storage
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from app.modules.users.models import User
from app.modules.users import service as users_service


def test_document_events_and_parsed_editor(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MINUTES_WORKER_ENABLED", False)
    monkeypatch.setattr(config, "DOCUMENT_PARSE_WORKER_ENABLED", False)
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_ENABLED", False)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    rpc = AsyncMock(return_value={"status": "parsed", "content": "Original parsed text", "metadata": [{"page_number": 1}]})
    monkeypatch.setattr(parsing, "sidecar", rpc)
    async def seed():
        await session.init_db()
        users = [await users_service.create_user("parse-events-" + uuid4().hex, "test", "product") for _ in range(2)]
        await session.close_db()
        return users
    users = asyncio.run(seed())
    tokens = [create_access_token(user.id, user.role, user.department) for user in users]
    try:
        with TestClient(create_app()) as client:
            headers = {"Authorization": "Bearer " + tokens[0]}
            other_headers = {"Authorization": "Bearer " + tokens[1]}
            base = client.post("/api/knowledge-bases", json={"name": "通知测试"}, headers=headers).json()["data"]
            root = f"/api/knowledge-bases/{base['id']}/documents"
            document = client.post(root + "/upload", files={"file": ("test.pdf", b"%PDF-1.4\nfixture")}, headers=headers).json()["data"]
            path = root + "/" + document["id"]
            with pytest.raises(WebSocketDisconnect) as failure:
                with client.websocket_connect("/api/knowledge-bases/events") as ws:
                    ws.send_json({"token": "invalid"})
                    ws.receive_json()
            assert failure.value.code == 4401
            with client.websocket_connect("/api/knowledge-bases/events") as ws:
                ws.send_json({"token": tokens[0]})
                assert ws.receive_json() == {"type": "documents.snapshot", "documents": []}
                assert client.post(path + "/parse", headers=headers).status_code == 200
                event = ws.receive_json()
                assert event["type"] == "document.updated" and event["document"]["status"] == "queued"
                row = client.portal.call(parsing.claim)
                assert ws.receive_json()["document"]["status"] == "parsing"
                client.portal.call(parsing.process, row)
                event = ws.receive_json()["document"]
                assert event["status"] == "parsed" and event["owner_id"] == users[0].id
                assert "content" not in event
                saved = client.get(path, headers=headers).json()["data"]
                blocks = [{"id": "p", "type": "paragraph", "content": [{"type": "text", "text": "Edited text", "styles": {}}]}]
                body = {"content": "Edited text", "blocks": blocks, "expected_parsed_at": saved["parsed_at"]}
                assert client.put(path + "/parsed", headers=other_headers, json=body).status_code == 404
                response = client.put(path + "/parsed", headers=headers, json=body)
                assert response.status_code == 200, response.text
                edited = response.json()["data"]
                assert edited["parse_content"] == "Edited text" and edited["parse_blocks"] == blocks
                assert edited["content"] == "" and edited["vectorized_at"] is None
                assert client.put(path + "/parsed", headers=headers, json=body).status_code == 409
                assert client.get(path + "/file", headers=headers).content == b"%PDF-1.4\nfixture"
            with client.websocket_connect("/api/knowledge-bases/events") as ws:
                ws.send_json({"token": tokens[0]})
                assert ws.receive_json()["documents"][0]["status"] == "parsed"
            with client.websocket_connect("/api/knowledge-bases/events") as ws:
                ws.send_json({"token": tokens[1]})
                assert ws.receive_json()["documents"] == []
    finally:
        async def cleanup():
            await session.init_db()
            async with session.transaction() as db:
                ids = [user.id for user in users]
                await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id.in_(
                    select(KnowledgeBase.id).where(KnowledgeBase.owner_id.in_(ids)))))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
            await session.close_db()
        asyncio.run(cleanup())
