"""撤销通过本机会话鉴权、事件落盘，并保留消息分支状态。"""
import asyncio
from datetime import datetime, timezone

import pytest
from uuid import uuid4

from src import config
from src.sessions import service
from src.sessions.storage import SessionStorage, SessionError
from src.tools.file_snapshots import SnapshotBatch


def test_session_undo_persists_and_rejects_other_owners_and_busy_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(service, 'storage', SessionStorage(tmp_path))
    root = config.WORKSPACE_DIR / 'general'
    root.mkdir(parents=True)
    (root / 'a').write_text('old')
    batch = SnapshotBatch(root, 7, ['a'])
    (root / 'a').write_text('new')
    change = batch.finish()[0]
    async def case():
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'undo-test', 'agent_id': 1}})
        messages = [{'id': 'reply', 'role': 'assistant', 'content': '已修改', 'status': 'complete',
                     'created_at': datetime.now(timezone.utc).isoformat(), 'context': {'file_changes': [change]}}]
        await service.operation('messages', {'owner_id': 7, 'thread_id': 'undo-test', 'body': {'messages': messages, 'expected_revision': 0}})
        params = {'owner_id': 7, 'thread_id': 'undo-test', 'body': {'change_id': change['id']}}
        with pytest.raises(SessionError):
            await service.operation('files.undo', {**params, 'owner_id': 8})
        def running(state):
            state['run_id'] = 'run'
            state['runs']['run'] = {'status': 'running'}
        service.storage.mutate(7, 'undo-test', 'fixture', running)
        with pytest.raises(SessionError, match='正在运行'):
            await service.operation('files.undo', params)
        service.storage.mutate(7, 'undo-test', 'fixture', lambda state: state.update(run_id=None))
        result = await service.operation('files.undo', params)
        assert result['change']['undone'] and (root / 'a').read_text() == 'old'
        loaded = await service.operation('get', {'owner_id': 7, 'thread_id': 'undo-test'})
        assert loaded['messages'][0]['context']['file_changes'][0]['undone']
        # 延迟到达的旧消息保存不能把已撤销状态覆盖掉。
        messages[0]['context']['file_changes'][0]['undone'] = False
        saved = await service.operation('messages', {'owner_id': 7, 'thread_id': 'undo-test', 'body': {
            'messages': messages, 'expected_revision': loaded['thread']['draft_revision']}})
        assert saved['message_branches'][0]['message']['context']['file_changes'][0]['undone']
        assert 'file_change_undone' in (tmp_path / 'sessions/7/undo-test.jsonl').read_text()
    asyncio.run(case())


def test_cancelled_stream_reconciles_disk_changes_before_undo(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(service, 'storage', SessionStorage(tmp_path))
    root = config.WORKSPACE_DIR / 'general'
    root.mkdir(parents=True)
    run_id = str(uuid4())
    batch = SnapshotBatch(root, 7, ['cancelled.txt'], run_id)
    (root / 'cancelled.txt').write_text('partial write')
    change = batch.finish()[0]
    async def case():
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'cancel-test', 'agent_id': 1}})
        def stopped(state):
            state['nodes']['reply'] = {'id': 'reply', 'role': 'assistant', 'content': '', 'context': {}, 'status': 'cancelled'}
            state['active_path'] = ['reply']
            state['runs'][run_id] = {'id': run_id, 'response_id': 'reply', 'status': 'cancelled'}
        service.storage.mutate(7, 'cancel-test', 'fixture', stopped)
        loaded = await service.operation('get', {'owner_id': 7, 'thread_id': 'cancel-test'})
        assert loaded['messages'][0]['context']['file_changes'][0]['id'] == change['id']
        await service.operation('files.undo', {'owner_id': 7, 'thread_id': 'cancel-test', 'body': {'change_id': change['id']}})
        assert not (root / 'cancelled.txt').exists()
    asyncio.run(case())
