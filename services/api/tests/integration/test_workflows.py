"""真实 PostgreSQL 验证注册冲突、纪要更新与批量写入回滚。"""

import asyncio
from uuid import uuid4

from app.infrastructure.database import session
from app.main import app
from app.modules.meetings.models import Minutes, TranscriptSegment
from app.modules.users.models import User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select


def test_registration_and_minutes_round_trip():
    async def case():
        suffix = uuid4().hex[:12]
        username, meeting_id = f"workflow_{suffix}", f"meeting-{suffix}"
        await session.init_db()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                credentials = {"username": username, "password": "test-password-123"}
                created = await client.post("/api/v1/auth/register", json=credentials)
                assert created.status_code == 201
                data = created.json()["data"]
                assert data["user"]["role"] == "member"
                assert data["user"]["department"] == "unassigned"
                duplicate = await client.post(
                    "/api/v1/auth/register",
                    json={**credentials, "password": "other-password-123"},
                )
                assert duplicate.status_code == 409
                assert duplicate.json()["data"] is None
                assert (
                    await client.post("/api/v1/auth/login", json=credentials)
                ).status_code == 200
                headers = {"Authorization": f"Bearer {data['token']}"}
                async with session.transaction() as db_session:
                    db_session.add(
                        Minutes(
                            id=f"minutes-{suffix}",
                            meeting_id=meeting_id,
                            title="Original",
                        )
                    )
                updated = await client.put(
                    f"/api/v1/meetings/{meeting_id}/minutes",
                    headers=headers,
                    json={"title": "Updated", "content": "Decision", "status": 1},
                )
                assert updated.status_code == 200
                empty = await client.put(
                    f"/api/v1/meetings/{meeting_id}/minutes", headers=headers, json={}
                )
                assert empty.status_code == 400
                loaded = await client.get(
                    f"/api/v1/meetings/{meeting_id}/minutes", headers=headers
                )
                assert loaded.json()["data"]["title"] == "Updated"
                assert loaded.json()["data"]["content"] == "Decision"
                assert loaded.json()["data"]["status"] == 1
                failed = await client.post(
                    "/api/v1/segments",
                    headers=headers,
                    json={
                        "meeting_id": meeting_id,
                        "segments": [
                            {"id": f"{suffix}-a", "seq": 0, "text": "A"},
                            {"id": f"{suffix}-b", "seq": 0, "text": "B"},
                        ],
                    },
                )
                assert failed.status_code == 500
                async with session.read_session() as db_session:
                    assert (
                        await db_session.scalar(
                            select(func.count())
                            .select_from(TranscriptSegment)
                            .where(TranscriptSegment.meeting_id == meeting_id)
                        )
                        == 0
                    )
        finally:
            async with session.transaction() as db_session:
                await db_session.execute(
                    delete(Minutes).where(Minutes.meeting_id == meeting_id)
                )
                await db_session.execute(
                    delete(TranscriptSegment).where(
                        TranscriptSegment.meeting_id == meeting_id
                    )
                )
                await db_session.execute(delete(User).where(User.username == username))
            await session.close_db()

    asyncio.run(case())
