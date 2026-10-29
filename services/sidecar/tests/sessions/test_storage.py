"""本地事件源、崩溃恢复和账号隔离。"""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from src.sessions.storage import SessionStorage, SessionError
from src.sessions.service import new_state


def create(store, key='thread1', owner=7):
    return store.mutate(owner, key, 'session_created', lambda state: state.update(new_state({'id': key, 'agent_id': 1})))


def test_rebuild_sqlite_from_jsonl_with_branches_and_tombstone(tmp_path):
    store = SessionStorage(tmp_path)
    create(store)
    def messages(state):
        state['nodes'] = {
            'u1': {'id':'u1', 'role':'user','content':'你好','status':'complete','parentId':None},
            'a1': {'id':'a1','role':'assistant','content':'你好！','status':'complete','parentId':'u1'},
            'a2': {'id':'a2','role':'assistant','content':'另一分支','status':'complete','parentId':'u1'}}
        state['active_path'] = ['u1','a2']
    store.mutate(7, 'thread1', 'messages_saved', messages)
    expected = store.get(7, 'thread1')
    file, _ = store.paths(7)
    file.unlink()
    rebuilt = SessionStorage(tmp_path)
    assert rebuilt.get(7, 'thread1') == expected
    assert len(rebuilt.list(7)) == 1
    assert len(rebuilt.get(7, 'thread1')['nodes']) == 3
    rebuilt.mutate(7, 'thread1', 'deleted', lambda s: s.update(deleted=True, nodes={}))
    file.unlink()
    with pytest.raises(SessionError, match='不存在'):
        SessionStorage(tmp_path).get(7, 'thread1')


def test_jsonl_durable_when_sqlite_commit_failed(tmp_path, monkeypatch):
    store = SessionStorage(tmp_path)
    create(store)
    original = store._project
    monkeypatch.setattr(store, '_project', lambda *args: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError):
        store.mutate(7, 'thread1', 'renamed', lambda s: s['thread'].update(title='已落盘'))
    monkeypatch.setattr(store, '_project', original)
    assert store.get(7, 'thread1')['thread']['title'] == '已落盘'


def test_partial_tail_truncated_but_complete_corruption_rejected(tmp_path):
    store = SessionStorage(tmp_path)
    create(store)
    file = store.paths(7)[1] / 'thread1.jsonl'
    good = file.read_bytes()
    with file.open('ab') as target:
        target.write(b'{"partial"')
    assert store.get(7, 'thread1')['thread']['id'] == 'thread1'
    assert file.read_bytes() == good
    with file.open('ab') as target:
        target.write(b'{"invalid":true}\n')
    with pytest.raises(SessionError, match='损坏'):
        store.get(7, 'thread1')


def test_owner_isolation_path_validation_and_serial_writes(tmp_path):
    store = SessionStorage(tmp_path)
    create(store)
    with pytest.raises(SessionError):
        store.get(8, 'thread1')
    with pytest.raises(SessionError):
        store.get(7, '../thread1')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.mutate(7, 'thread1', 'increment',
                      lambda s: s['thread'].update(draft_revision=s['thread']['draft_revision'] + 1)), range(20)))
    assert store.get(7, 'thread1')['thread']['draft_revision'] == 20
    events = [json.loads(line) for line in (store.paths(7)[1]/'thread1.jsonl').read_text().splitlines()]
    assert [e['ordinal'] for e in events] == list(range(1,22))


def test_delete_purges_content_and_survives_replace_before_index_commit(tmp_path,monkeypatch):
    store=SessionStorage(tmp_path)
    create(store)
    store.mutate(7,'thread1','draft',lambda s:s['thread'].update(draft='PRIVATE_CONTENT'))
    def remove(state):
        state.update(deleted=True,nodes={},runs={},approvals={},steering={},active_path=[],knowledge_base_ids=[])
        state['thread'].update(title='已删除',draft='')
    store.mutate(7,'thread1','deleted',remove)
    original=store._project
    monkeypatch.setattr(store,'_project',lambda *args:(_ for _ in ()).throw(OSError('crash after replace')))
    with pytest.raises(OSError):store.purge_deleted(7,'thread1')
    monkeypatch.setattr(store,'_project',original)
    assert 'PRIVATE_CONTENT' not in (store.paths(7)[1]/'thread1.jsonl').read_text()
    with pytest.raises(SessionError,match='不存在'):store.get(7,'thread1')
    database,_=store.paths(7)
    database.unlink()
    assert SessionStorage(tmp_path).get(7,'thread1',deleted=True)['deleted']
