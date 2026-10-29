"""停止后以新运行继续，只带当前分支证据，不复用旧检查点或审批。"""
import asyncio
import copy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from src import config
from src.agents import agent
from src.providers.llm.schemas import ModelSettings
from src.sessions import service
from src.sessions.progress import execution_context, MAX_CONTEXT
from src.sessions.storage import SessionStorage, SessionError
from src.transport import handlers
from src.transport.handlers import AgentInput


def fixture():
    run_id = str(uuid4())
    return {'thread': {'project_id': None}, 'runs': {run_id: {'id': run_id, 'status': 'cancelled', 'response_id': 'a', 'request_message_id': 'u', 'project_id': None}},
            'nodes': {'u': {'id': 'u', 'role': 'user', 'content': '创建两个文件'},
                      'a': {'id': 'a', 'role': 'assistant', 'status': 'cancelled', 'content': '第一个已完成', 'context': {
                          'execution_run_id': run_id, 'tool_calls': [
                              {'id': 'one', 'name': 'write_file', 'args': {'file_path': 'a.txt'}, 'status': 'complete', 'result': 'written'},
                              {'id': 'two', 'name': 'execute', 'args': {'command': 'create b'}, 'status': 'cancelled'}],
                          'file_changes': [{'path': '/project/a.txt', 'kind': 'created', 'undone': True}]}},
                      'other': {'id': 'other', 'role': 'assistant', 'content': 'other-branch-secret', 'context': {'tool_calls': [{'name': 'read_file', 'result': 'other-branch-secret'}]}}}}


def test_progress_is_branch_scoped_and_marks_uncertain_outcomes_and_undo():
    state = fixture()
    context = execution_context(state, ['u', 'a'], [{'content': '创建两个文件'}])
    record = json.loads(context)[0]
    assert record['request'] == '创建两个文件' and record['partial_reply'] == '第一个已完成'
    assert [tool['status'] for tool in record['tools']] == ['returned', 'cancelled']
    assert record['files'][0]['undone']
    assert 'other-branch-secret' not in context
    state['thread']['project_id'] = str(uuid4())
    assert execution_context(state, ['u', 'a'], []) == ''


def test_progress_is_bounded_and_tolerates_old_metadata():
    state = fixture()
    tool = state['nodes']['a']['context']['tool_calls'][0]
    tool.update(args={'long': 'x' * 100000}, result='x' * 100000)
    context = execution_context(state, ['u', 'a'], [])
    assert len(context) <= MAX_CONTEXT and json.loads(context)[0]['tools'][0]['result_truncated']
    assert execution_context(state, ['u', 'a'], [{'content': 'x' * 119900}]) == ''
    state['nodes']['a']['context'].update(tool_calls=['broken', {}], usage=[], file_changes='broken')
    assert json.loads(execution_context(state, ['u', 'a'], []))[0]['status'] == 'cancelled'


def test_next_run_receives_progress_before_latest_user_instruction(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    progress = execution_context(fixture(), ['u', 'a'], [])
    class Inspect(FakeMessagesListChatModel):
        def bind_tools(self, *args, **kwargs):
            return self
        async def _agenerate(self, messages, **kwargs):
            assert messages[-1].content == '接着运行，但不要删除文件'
            assert '<historical_execution_data>' in messages[-2].content
            assert 'write_file' in messages[-2].content
            assert 'cancelled' in messages[-2].content
            return await super()._agenerate(messages, **kwargs)
    monkeypatch.setattr(agent, 'create_model', lambda *_: Inspect(responses=[AIMessage('先核验文件，再处理剩余工作')]))
    async def case():
        body = AgentInput(thread_id='continue', messages=[{'role': 'user', 'content': '接着运行，但不要删除文件'}], execution_context=progress)
        events = [event async for event in agent.run_agent(body, ModelSettings(model='fixture', timeout=10))]
        assert events[-1]['type'] == 'done', events
    asyncio.run(case())


def test_cancel_then_continue_creates_new_run_with_durable_tool_results(monkeypatch, tmp_path):
    store = SessionStorage(tmp_path)
    monkeypatch.setattr(service, 'storage', store)
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(agent, 'settings_for', lambda _: SimpleNamespace(model='test'))
    captured = []
    started = asyncio.Event()
    async def fake_chat(params, state):
        captured.append(copy.deepcopy(params))
        async def events():
            yield {'type': 'start'}
            if len(captured) == 1:
                yield {'type': 'tool_call', 'id': 'write', 'name': 'write_file', 'args': {'file_path': 'a.txt'}}
                yield {'type': 'tool_result', 'id': 'write', 'content': 'a.txt saved', 'status': 'success'}
                yield {'type': 'tool_call', 'id': 'unknown', 'name': 'execute', 'args': {'command': 'work'}}
                yield {'type': 'delta', 'text': '第一步已完成'}
                started.set()
                await asyncio.Event().wait()
            else:
                yield {'type': 'done', 'content': '继续完成剩余工作'}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        service.ACTIVE.clear()
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'continue', 'agent_id': 1}})
        timestamp = datetime.now(timezone.utc).isoformat()
        messages = [{'id': 'u', 'role': 'user', 'content': '创建两个文件', 'created_at': timestamp, 'context': {}},
                    {'id': 'a', 'role': 'assistant', 'content': '', 'status': 'streaming', 'created_at': timestamp, 'context': {}}]
        detail = await service.operation('messages', {'owner_id': 7, 'thread_id': 'continue', 'body': {'messages': messages, 'expected_revision': 0}})
        async def collect():
            stream = await service.open_chat({'owner_id': 7, 'thread_id': 'continue', 'body': {
                'thread_id': 'continue', 'response_id': 'a', 'expected_revision': detail['thread']['draft_revision']}}, None)
            return [event async for event in stream.events]
        task = asyncio.create_task(collect())
        await asyncio.wait_for(started.wait(), 3)
        old_id = captured[0]['run_id']
        await service.operation('runs.cancel', {'owner_id': 7, 'body': {'run_id': old_id}})
        with pytest.raises(asyncio.CancelledError):
            await task
        detail = await service.operation('get', {'owner_id': 7, 'thread_id': 'continue'})
        assert detail['messages'][-1]['content'] == '第一步已完成'
        # 使用持久化后的数据继续，不能只依赖前端的内存。
        monkeypatch.setattr(service, 'storage', SessionStorage(tmp_path))
        followup = [*detail['messages'], {'id': 'u2', 'role': 'user', 'content': '接着运行', 'created_at': timestamp, 'context': {}},
                    {'id': 'a2', 'role': 'assistant', 'content': '', 'status': 'streaming', 'created_at': timestamp, 'context': {}}]
        detail = await service.operation('messages', {'owner_id': 7, 'thread_id': 'continue', 'body': {'messages': followup, 'expected_revision': detail['thread']['draft_revision']}})
        stream = await service.open_chat({'owner_id': 7, 'thread_id': 'continue', 'body': {
            'thread_id': 'continue', 'response_id': 'a2', 'expected_revision': detail['thread']['draft_revision']}}, None)
        assert [event async for event in stream.events][-1]['type'] == 'done'
        assert captured[1]['run_id'] != old_id and captured[1]['approval_resume'] is None
        records = json.loads(captured[1]['execution_context'])
        assert records[0]['run_id'] == old_id and records[0]['request'] == '创建两个文件'
        assert records[0]['tools'][0]['result_preview'] == 'a.txt saved'
        assert records[0]['tools'][1]['status'] == 'cancelled'
        assert captured[1]['messages'][-1]['content'] == '接着运行'
        assert service.ACTIVE == {}
    asyncio.run(case())


def test_new_run_waits_until_previous_cleanup_has_finished(monkeypatch, tmp_path):
    store = SessionStorage(tmp_path)
    monkeypatch.setattr(service, 'storage', store)
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(agent, 'settings_for', lambda _: SimpleNamespace(model='test'))
    async def case():
        service.ACTIVE.clear()
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'cleanup', 'agent_id': 1}})
        run_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        def stopped(state):
            state['nodes'].update({
                'u': {'id': 'u', 'role': 'user', 'content': 'continue', 'context': {}, 'created_at': timestamp},
                'a': {'id': 'a', 'role': 'assistant', 'content': '', 'status': 'streaming', 'context': {}, 'created_at': timestamp}})
            state['active_path'] = ['u', 'a']
            state['runs'][run_id] = {'id': run_id, 'status': 'cancelled', 'response_id': 'old'}
        store.mutate(7, 'cleanup', 'fixture', stopped)
        task = asyncio.create_task(asyncio.Event().wait())
        service.ACTIVE[7, run_id] = task
        try:
            with pytest.raises(SessionError, match='上一轮仍在停止'):
                await service.open_chat({'owner_id': 7, 'thread_id': 'cleanup', 'body': {
                    'thread_id': 'cleanup', 'response_id': 'a', 'expected_revision': 0}}, None)
            assert store.get(7, 'cleanup')['run_id'] is None
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            service.ACTIVE.clear()
    asyncio.run(case())


def test_close_before_first_event_releases_registered_run(monkeypatch, tmp_path):
    store = SessionStorage(tmp_path)
    monkeypatch.setattr(service, 'storage', store)
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(agent, 'settings_for', lambda _: SimpleNamespace(model='test'))
    async def fake_chat(*_):
        async def events():
            pytest.fail('提前取消不能开始模型执行')
            yield {}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        service.ACTIVE.clear()
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'early', 'agent_id': 1}})
        timestamp = datetime.now(timezone.utc).isoformat()
        detail = await service.operation('messages', {'owner_id': 7, 'thread_id': 'early', 'body': {'expected_revision': 0, 'messages': [
            {'id': 'u', 'role': 'user', 'content': 'start', 'created_at': timestamp, 'context': {}},
            {'id': 'a', 'role': 'assistant', 'content': '', 'status': 'streaming', 'created_at': timestamp, 'context': {}}]}})
        stream = await service.open_chat({'owner_id': 7, 'thread_id': 'early', 'body': {
            'thread_id': 'early', 'response_id': 'a', 'expected_revision': detail['thread']['draft_revision']}}, None)
        assert service.ACTIVE
        await stream.aclose()
        saved = store.get(7, 'early')
        assert saved['run_id'] is None and saved['nodes']['a']['status'] == 'cancelled'
        assert service.ACTIVE == {}
    asyncio.run(case())
