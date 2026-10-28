"""审批先持久化再返回，恢复原设备，拒绝重复决定与跨用户访问。"""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from src.core.exceptions import ApiError
from src.infrastructure.database import session
from src.infrastructure.sidecar.context import execution_scope, scope
from src.modules.agents import approval_service, conversation_service, run_service, service
from src.modules.agents.approval_models import AgentApproval
from src.modules.agents.run_models import AgentRun
from tests.integration.test_agent_runs_db import prepared, Stream

INTERRUPTS = [{'id': 'interrupt-one', 'value': {'action_requests': [
    {'name': 'write_file', 'args': {'file_path': 'report.md', 'content': 'reviewed'}}]}}]


@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_pause_refresh_decision_and_resume_original_device(monkeypatch, decision):
    async def case():
        async with prepared() as (owner, key, body):
            original_device = str(uuid4())
            paused = Stream([{'type': 'start'}, {'type': 'delta', 'text': '执行前。'}, {'type': 'approval', 'interrupts': INTERRUPTS}])
            connection = AsyncMock(return_value=paused)
            monkeypatch.setattr(service, 'open_chat', connection)
            with execution_scope(owner.id, original_device):
                stream = await conversation_service.open_chat(owner.id, key, body)
            chunks = [chunk async for chunk in stream.chunks()]
            assert b'approval_id' in b''.join(chunks) and paused.closed
            records = await approval_service.list_approvals(owner.id, key)
            approval = records[0]
            assert approval['actionable'] and approval['status'] == 'pending'
            # 页面刷新和原 SSE 关闭均不能撤销已持久化的等待。
            detail = await conversation_service.get(owner.id, key)
            assert detail['messages'][-1]['content'] == '执行前。'
            assert detail['messages'][-1]['status'] == 'waiting_approval'
            assert (await run_service.get(owner.id, stream.token))['status'] == 'running'
            assert await approval_service.list_approvals(owner.id + 999999, key) == []
            with pytest.raises(ApiError) as error:
                await approval_service.decide(owner.id + 999999, approval['id'], decision)
            assert error.value.status_code == 404
            async def resumed(payload, owner_id, **kwargs):
                assert scope.get() == (owner.id, original_device)
                assert kwargs['run_id'] == stream.token
                assert kwargs['approval_resume'] == {'interrupt-one': {'decisions': [{'type': decision}]}}
                return Stream([{'type': 'start'}, {'type': 'delta', 'text': '继续回答。'}, {'type': 'done', 'content': '继续回答。'}])
            monkeypatch.setattr(service, 'open_chat', resumed)
            # 即使当前页面来自其他设备，执行依然恢复到原设备。
            with execution_scope(owner.id, str(uuid4())):
                next_stream = await approval_service.decide(owner.id, approval['id'], decision)
            with pytest.raises(ApiError) as error:
                await approval_service.decide(owner.id, approval['id'], decision)
            assert error.value.status_code == 409
            async for _ in next_stream.chunks():
                pass
            detail = await conversation_service.get(owner.id, key)
            assert detail['messages'][-1]['content'] == '执行前。继续回答。'
            assert (await run_service.get(owner.id, stream.token))['status'] == 'completed'
            records = await approval_service.list_approvals(owner.id, key)
            assert records[0]['status'] == ('approved' if decision == 'approve' else 'rejected')
            assert not records[0]['actionable']
    asyncio.run(case())


def test_cancelled_approval_cannot_resume(monkeypatch):
    async def case():
        async with prepared() as (owner, key, body):
            monkeypatch.setattr(service, 'open_chat', AsyncMock(return_value=Stream([{'type': 'approval', 'interrupts': INTERRUPTS}])))
            stream = await conversation_service.open_chat(owner.id, key, body)
            async for _ in stream.chunks(): pass
            approval = (await approval_service.list_approvals(owner.id, key))[0]
            await run_service.cancel(owner.id, stream.token)
            with pytest.raises(ApiError) as error:
                await approval_service.decide(owner.id, approval['id'], 'approve')
            assert error.value.status_code == 409
            assert not (await approval_service.list_approvals(owner.id, key))[0]['actionable']
    asyncio.run(case())


def test_concurrent_decisions_execute_only_once(monkeypatch):
    async def case():
        async with prepared() as (owner, key, body):
            monkeypatch.setattr(service, 'open_chat', AsyncMock(return_value=Stream([{'type': 'approval', 'interrupts': INTERRUPTS}])))
            stream = await conversation_service.open_chat(owner.id, key, body)
            async for _ in stream.chunks(): pass
            approval = (await approval_service.list_approvals(owner.id, key))[0]
            resume = AsyncMock(return_value=Stream([{'type': 'done', 'content': '完成'}]))
            monkeypatch.setattr(service, 'open_chat', resume)
            results = await asyncio.gather(approval_service.decide(owner.id, approval['id'], 'approve'),
                approval_service.decide(owner.id, approval['id'], 'reject'), return_exceptions=True)
            assert resume.await_count == 1
            assert sum(isinstance(result, ApiError) and result.status_code == 409 for result in results) == 1
            successful = next(result for result in results if not isinstance(result, BaseException))
            async for _ in successful.chunks(): pass
    asyncio.run(case())


def test_expired_approval_does_not_resume(monkeypatch):
    from datetime import datetime, timedelta, timezone
    async def case():
        async with prepared() as (owner, key, body):
            upstream = AsyncMock(return_value=Stream([{'type': 'approval', 'interrupts': INTERRUPTS}]))
            monkeypatch.setattr(service, 'open_chat', upstream)
            stream = await conversation_service.open_chat(owner.id, key, body)
            async for _ in stream.chunks(): pass
            approval = (await approval_service.list_approvals(owner.id, key))[0]
            async with session.transaction() as db:
                run = await db.get(AgentRun, stream.token)
                run.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            with pytest.raises(ApiError) as error:
                await approval_service.decide(owner.id, approval['id'], 'approve')
            assert error.value.status_code == 409
            assert upstream.await_count == 1
    asyncio.run(case())


def test_unavailable_device_fails_without_replaying_decision(monkeypatch):
    from src.core.responses import ApiCode
    async def case():
        async with prepared() as (owner, key, body):
            monkeypatch.setattr(service, 'open_chat', AsyncMock(return_value=Stream([{'type': 'approval', 'interrupts': INTERRUPTS}])))
            stream = await conversation_service.open_chat(owner.id, key, body)
            async for _ in stream.chunks(): pass
            approval = (await approval_service.list_approvals(owner.id, key))[0]
            monkeypatch.setattr(service, 'open_chat', AsyncMock(side_effect=ApiError(ApiCode.INTERNAL_ERROR, '设备离线', 503)))
            with pytest.raises(ApiError):
                await approval_service.decide(owner.id, approval['id'], 'approve')
            assert (await run_service.get(owner.id, stream.token))['status'] == 'failed'
            with pytest.raises(ApiError) as error:
                await approval_service.decide(owner.id, approval['id'], 'approve')
            assert error.value.status_code == 409
    asyncio.run(case())
