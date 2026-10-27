"""真实 PostgreSQL 任务事务与模型 HTTP 替身联调。"""
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import httpx
from sqlalchemy import delete, select, update, func
from src.core import config
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.meetings import generation
from src.modules.meetings.models import Meeting, MeetingGenerationJob
from src.modules.users.models import User
from src.modules.users import service as users_service


async def setup(client, user):
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.role, user.department)}"}
    workspace = (await client.post("/api/meetings", headers=headers, json={"title": "测试会议"})).json()["data"]
    path = f'/api/meetings/{workspace["meeting"]["id"]}'
    workspace["meeting"]["status"] = "ended"
    workspace["segments"] = [{"id": "segment-1", "seq": 0, "revision": 1, "speaker": "说话人1", "text": "修正后的原始内容", "start_ms": 0, "end_ms": 1000}]
    workspace = (await client.put(path, headers=headers, json={**workspace, "expected_revision": workspace["meeting"]["revision"]})).json()["data"]
    return headers, path, workspace


def test_persistent_generation_success_failure_and_lease_recovery(monkeypatch):
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "internal-test")
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"generate-{uuid4().hex}", "test", "product"))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
                headers, path, workspace = await setup(client, owners[0])
                endpoint = path + "/minutes/generate"
                body = {"expected_revision": workspace["meeting"]["revision"]}
                assert (await client.post(endpoint, json=body)).status_code == 401
                other = {"Authorization": f"Bearer {create_access_token(owners[1].id, owners[1].role, owners[1].department)}"}
                assert (await client.post(endpoint, headers=other, json=body)).status_code == 404
                assert (await client.post(endpoint, headers=headers, json={"expected_revision": 1})).status_code == 409
                responses = await asyncio.gather(*[client.post(endpoint, headers=headers, json=body) for _ in range(2)])
                assert all(response.status_code == 200 for response in responses)
                accepted = responses[0].json()["data"]
                assert accepted["task_id"] == responses[1].json()["data"]["task_id"]
                assert accepted["source_revision"] == workspace["meeting"]["revision"]
                async with session.read_session() as db:
                    job = await db.get(MeetingGenerationJob, accepted["task_id"])
                    assert job.input["segments"][0]["text"] == "修正后的原始内容"
                    assert job.status == "queued"
                # 生成期间旧页面不能修改输入或把状态伪装成完成。
                pending = (await client.get(path, headers=headers)).json()["data"]
                pending["segments"][0]["text"] = "不应写入"
                assert (await client.put(path, headers=headers, json={**pending, "expected_revision": pending["meeting"]["revision"]})).status_code == 409
                # 数据库重连模拟执行器重启，排队快照仍完整。
                await session.close_db()
                await session.init_db()
                calls = []
                async def model(request):
                    import json
                    data = json.loads(request.content)
                    calls.append(data)
                    assert request.headers["X-Internal-Token"] == "internal-test"
                    await asyncio.sleep(0.01)
                    return httpx.Response(200, json={"task_id": data["task_id"], "source_revision": data["source_revision"],
                        "content": "# 测试会议\n\n## 明确结论\n先做 PDF。", "model": "fixture-model", "prompt_version": "minutes-v1"})
                results = await asyncio.gather(generation.run_once(httpx.MockTransport(model)), generation.run_once(httpx.MockTransport(model)))
                assert sorted(results) == [False, True]
                assert len(calls) == 1
                ready = (await client.get(path, headers=headers)).json()["data"]
                assert ready["meeting"]["generation_status"] == "ready"
                assert ready["minutes"]["content"].startswith("# 测试会议")
                assert ready["minutes"]["blocks"] is None
                async with session.read_session() as db:
                    job = await db.get(MeetingGenerationJob, accepted["task_id"])
                    assert job.status == "succeeded" and job.result["prompt_version"] == "minutes-v1"
                # 失败保留已有纪要；新任务采用独立 ID，可再次提交。
                response = await client.post(endpoint, headers=headers, json={"expected_revision": ready["meeting"]["revision"]})
                task2 = response.json()["data"]["task_id"]
                assert task2 != accepted["task_id"]
                await generation.run_once(httpx.MockTransport(lambda request: httpx.Response(502, json={"detail": {"code": "MODEL_NOT_CONFIGURED", "message": "private upstream"}})))
                failed = (await client.get(path, headers=headers)).json()["data"]
                assert failed["meeting"]["generation_status"] == "failed"
                assert "ARK_API_KEY" in failed["meeting"]["generation_error"]
                assert "private" not in failed["meeting"]["generation_error"]
                assert failed["minutes"] == ready["minutes"]
                response = await client.post(endpoint, headers=headers, json={"expected_revision": failed["meeting"]["revision"]})
                task3 = response.json()["data"]["task_id"]
                async with session.transaction() as db:
                    await db.execute(update(MeetingGenerationJob).where(MeetingGenerationJob.id == task3).values(
                        status="running", attempts=1, claim_token="old-claim", lease_until=datetime.now(timezone.utc) - timedelta(seconds=30)))
                await generation.run_once(httpx.MockTransport(model))
                await generation.finish(task3, "old-claim", None, "不应覆盖新的结果")
                restored = (await client.get(path, headers=headers)).json()["data"]
                assert restored["meeting"]["generation_status"] == "ready"
                assert restored["meeting"]["generation_error"] is None
                async with session.read_session() as db:
                    assert (await db.get(MeetingGenerationJob, task3)).attempts == 2
                assert (await client.delete(path, headers=headers)).status_code == 200
                async with session.read_session() as db:
                    assert await db.scalar(select(func.count()).select_from(MeetingGenerationJob).where(MeetingGenerationJob.meeting_id == workspace["meeting"]["id"])) == 0
        finally:
            async with session.transaction() as db:
                await db.execute(delete(Meeting).where(Meeting.owner_id.in_([owner.id for owner in owners])))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
