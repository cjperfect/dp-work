"""验证会议 PostgreSQL 持久化、版本冲突与账号隔离。"""
import asyncio
from uuid import uuid4
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, func
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.meetings.models import Meeting, MeetingSegment, MeetingMinutes
from src.modules.users.models import User
from src.modules.users import service as users_service


def test_meeting_lifecycle_and_legacy_import():
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"meeting-{uuid4().hex}", "test", "product"))
            headers = [{"Authorization": f"Bearer {create_access_token(user.id, user.role, user.department)}"} for user in owners]
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                assert (await client.get("/api/meetings")).status_code == 401
                response = await client.post("/api/meetings", headers=headers[0], json={"title": " 评审会议 "})
                assert response.status_code == 200, response.text
                workspace = response.json()["data"]
                assert workspace["meeting"]["title"] == "评审会议"
                assert workspace["meeting"]["resumed_at"].endswith("Z")
                path = f'/api/meetings/{workspace["meeting"]["id"]}'
                assert (await client.get(path, headers=headers[1])).status_code == 404
                assert (await client.delete(path, headers=headers[1])).status_code == 404
                assert (await client.put(path, headers=headers[1], json={**workspace, "expected_revision": 1})).status_code == 404
                assert (await client.get("/api/meetings", headers=headers[1])).json()["data"] == []
                workspace["meeting"].update(status="paused", elapsed_ms=9000)
                workspace["segments"] = [{"id": "segment1", "seq": 1, "text": "确认的转写🙂", "speaker": "说话人1", "start_ms": 0, "end_ms": 1000}]
                blocks = [{"id": "block1", "type": "paragraph", "content": [{"type": "text", "text": "结论", "styles": {"bold": True}}]}]
                workspace["minutes"] = {"content": "**结论**", "blocks": blocks, "status": 1, "archived_document_id": None}
                saved = await client.put(path, headers=headers[0], json={**workspace, "expected_revision": 1})
                assert saved.status_code == 200, saved.text
                workspace = saved.json()["data"]
                assert workspace["meeting"]["resumed_at"] is None
                assert workspace["meeting"]["revision"] == 2
                assert (await client.put(path, headers=headers[0], json={**workspace, "expected_revision": 1})).status_code == 409
                # 序号冲突时，整笔事务（包括会议标题）回滚。
                conflicting = {**workspace, "meeting": {**workspace["meeting"], "title": "不应写入"}, "segments": [{**workspace["segments"][0], "id": "another"}], "expected_revision": 2}
                assert (await client.put(path, headers=headers[0], json=conflicting)).status_code == 409
                unchanged = (await client.get(path, headers=headers[0])).json()["data"]
                assert unchanged == workspace
                workspace["meeting"].update(status="ended", generation_status="generating", minutes_status=0)
                # 重复片段只更新原行；遗漏已有片段时不删除确认转写。
                workspace["segments"][0].update(revision=2, text="修订的转写")
                saved = await client.put(path, headers=headers[0], json={**workspace, "expected_revision": 2})
                assert saved.status_code == 200, saved.text
                workspace = saved.json()["data"]
                assert workspace["meeting"]["ended_at"]
                saved = await client.put(path, headers=headers[0], json={**workspace, "segments": [], "expected_revision": 3})
                assert saved.status_code == 200, saved.text
                workspace = saved.json()["data"]
                assert len(workspace["segments"]) == 1
                # 旧浏览器副本不能覆盖 PostgreSQL 最新内容。
                legacy = {**workspace, "meeting": {**workspace["meeting"], "title": "旧浏览器标题"}}
                imported = await client.post("/api/meetings/import", headers=headers[0], json=legacy)
                assert imported.json()["data"]["meeting"]["title"] == "评审会议"
                assert (await client.post("/api/meetings/import", headers=headers[1], json=legacy)).status_code == 404
                # 关闭并重新建立数据库连接后，完整恢复富文本和状态。
                await session.close_db()
                await session.init_db()
                restored = (await client.get(path, headers=headers[0])).json()["data"]
                assert restored == workspace
                assert restored["minutes"]["blocks"] == blocks
                assert restored["segments"][0]["text"] == "修订的转写"
                assert (await client.get("/api/meetings", headers=headers[0])).json()["data"][0]["generation_status"] == "idle"
                async with session.read_session() as db:
                    assert await db.scalar(select(func.count()).select_from(MeetingSegment).where(MeetingSegment.meeting_id == workspace["meeting"]["id"])) == 1
                assert (await client.delete(path, headers=headers[0])).status_code == 200
                assert (await client.get(path, headers=headers[0])).status_code == 404
                assert (await client.put(path, headers=headers[0], json={**workspace, "expected_revision": 4})).status_code == 404
                async with session.read_session() as db:
                    assert await db.get(MeetingMinutes, workspace["meeting"]["id"]) is None
                    assert await db.scalar(select(func.count()).select_from(MeetingSegment).where(MeetingSegment.meeting_id == workspace["meeting"]["id"])) == 0
                # 独立旧记录可以迁移，并且重复导入不会产生副本。
                legacy["meeting"]["id"] = str(uuid4())
                legacy["minutes"]["status"] = 2
                for _ in range(2):
                    imported = await client.post("/api/meetings/import", headers=headers[0], json=legacy)
                    assert imported.status_code == 200, imported.text
                assert len((await client.get("/api/meetings", headers=headers[0])).json()["data"]) == 1
        finally:
            async with session.transaction() as db:
                await db.execute(delete(Meeting).where(Meeting.owner_id.in_([owner.id for owner in owners])))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
