"""生成状态通知需要登录，使用 PostgreSQL 通知跨连接推送。"""
import asyncio
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import delete
from src.core import config
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.meetings import generation
from src.modules.meetings.models import Meeting
from src.modules.users.models import User
from src.modules.users import service as users_service


def test_owner_scoped_generation_events(monkeypatch):
    monkeypatch.setattr(config, "MINUTES_WORKER_ENABLED", False)
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_ENABLED", False)
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "internal-test")
    async def seed():
        await session.init_db()
        users = [await users_service.create_user(f"events-{uuid4().hex}", "test", "product") for _ in range(2)]
        await session.close_db()
        return users
    users = asyncio.run(seed())
    tokens = [create_access_token(user.id, user.role, user.department) for user in users]
    try:
        with TestClient(create_app()) as client:
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect("/api/meetings/events") as websocket:
                    websocket.send_json({"token": "invalid"})
                    websocket.receive_json()
            assert error.value.code == 4401
            headers = {"Authorization": f"Bearer {tokens[0]}"}
            workspace = client.post("/api/meetings", headers=headers, json={"title": "状态通知测试"}).json()["data"]
            path = f'/api/meetings/{workspace["meeting"]["id"]}'
            workspace["meeting"]["status"] = "ended"
            workspace["segments"] = [{"id": "one", "seq": 0, "text": "讨论内容", "start_ms": 0}]
            workspace = client.put(path, headers=headers, json={**workspace, "expected_revision": 1}).json()["data"]
            with client.websocket_connect("/api/meetings/events") as other:
                other.send_json({"token": tokens[1]})
                assert other.receive_json()["meetings"] == []
            with client.websocket_connect("/api/meetings/events") as websocket:
                websocket.send_json({"token": tokens[0]})
                snapshot = websocket.receive_json()
                assert snapshot["type"] == "meetings.snapshot"
                assert all(row["owner_id"] == users[0].id for row in snapshot["meetings"])
                response = client.post(path + "/minutes/generate", headers=headers, json={"expected_revision": 2})
                assert response.status_code == 200
                event = websocket.receive_json()
                assert event["type"] == "meeting.updated" and event["meeting"]["generation_status"] == "generating"
                def model(request):
                    import json
                    source = json.loads(request.content)
                    return httpx.Response(200, json={"task_id": source["task_id"], "source_revision": source["source_revision"],
                        "content": "# 已生成纪要", "model": "test", "prompt_version": "minutes-v1"})
                assert client.portal.call(generation.run_once, httpx.MockTransport(model))
                event = websocket.receive_json()
                assert event["meeting"]["generation_status"] == "ready"
                assert event["meeting"]["id"] == workspace["meeting"]["id"]
                assert client.delete(path, headers=headers).status_code == 200
                assert websocket.receive_json() == {"type": "meeting.removed", "meeting_id": workspace["meeting"]["id"]}
    finally:
        async def cleanup():
            await session.init_db()
            async with session.transaction() as db:
                await db.execute(delete(Meeting).where(Meeting.owner_id.in_([user.id for user in users])))
                await db.execute(delete(User).where(User.id.in_([user.id for user in users])))
            await session.close_db()
        asyncio.run(cleanup())
