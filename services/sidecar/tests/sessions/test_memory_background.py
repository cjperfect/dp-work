"""自动记忆的空闲筛选、恢复、合并和遗忘边界。"""
import asyncio
import copy
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest
from src import config
from src.memory import jobs, pipeline, repository as repo
from src.memory.schemas import MemoryWrite, MemoryUpdate, MemoryQuery, MemoryPreference
from src.memory.worker import MemoryWorker, candidates
from src.sessions.service import new_state
from src.sessions.storage import SessionStorage
from src.providers.llm.schemas import ModelSettings


@pytest.fixture(autouse=True)
def isolated_model_settings(monkeypatch):
    monkeypatch.setattr(config, 'EMBEDDING_API_KEY', '')
    from src.providers import local_settings
    monkeypatch.setattr(local_settings, 'runtime', lambda *args: None)


def fixture_state():
    stamp = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    state = new_state({'id': 'memory-thread', 'agent_id': 1})
    state['thread']['updated_at'] = stamp
    state['active_path'] = ['u1', 'a1']
    state['nodes'] = {
        'u1': {'id':'u1','role':'user','status':'complete','content':'以后写代码注释保持简洁，只说明函数作用，不要逐行解释实现逻辑。这个习惯适用于所有项目。','created_at':stamp,'context':{}},
        'a1': {'id':'a1','role':'assistant','status':'complete','content':'明白，后续注释将保持简洁，只描述当前函数作用，必要时才说明约束条件，不逐行解释实现。','created_at':stamp,'context':{}},
    }
    return state


def candidate(**changes):
    return {'title':'代码注释习惯','content':'代码注释简洁，只说明函数作用。','scope':'user','kind':'preference','confidence':0.95,
            'evidence':[{'message_id':'u1','quote':'代码注释保持简洁'}], **changes}


def save_state(store, state, owner=1):
    store.mutate(owner, state['thread']['id'], 'fixture', lambda value: value.update(copy.deepcopy(state)))


def test_scan_ignores_active_recent_and_deleted(monkeypatch, tmp_path):
    store = SessionStorage(tmp_path)
    state = fixture_state()
    save_state(store, state)
    assert candidates(tmp_path) == [(1,'memory-thread')]
    state['thread']['updated_at'] = datetime.now(timezone.utc).isoformat()
    save_state(store, state)
    assert candidates(tmp_path) == []
    state = fixture_state(); state['runs']['r'] = {'id':'r','status':'running'}
    assert jobs.prepare(1,state,tmp_path) is None
    state['runs'] = {};state['thread']['draft'] = '正在输入'
    assert jobs.prepare(1,state,tmp_path) is None
    state['thread']['draft'] = '';state['deleted'] = True
    assert jobs.prepare(1,state,tmp_path) is None


def test_atomic_claim_lease_and_crash_recovery(tmp_path):
    state = fixture_state()
    first = jobs.prepare(1,state,tmp_path)
    assert first and jobs.prepare(1,state,tmp_path) is None
    with repo.connection(1,tmp_path,True) as db:
        db.execute('UPDATE memory_jobs SET lease_until=0')
    second = jobs.prepare(1,state,tmp_path)
    assert second['token'] != first['token']
    assert not jobs.commit(1,first,state,[],[],[],tmp_path)
    assert jobs.commit(1,second,state,[],[],[],tmp_path)
    assert jobs.prepare(1,state,tmp_path) is None


def test_two_stage_generation_and_no_duplicate_on_restart(monkeypatch,tmp_path):
    state=fixture_state();store=SessionStorage(tmp_path);save_state(store,state)
    calls=[]
    async def fake_complete(messages,settings,transport=None):
        calls.append(messages)
        if len(calls)==1:
            return json.dumps({'memories':[candidate()]},ensure_ascii=False),'test'
        return json.dumps({'decisions':[{'candidate':0,'action':'add'}]}),'test'
    monkeypatch.setattr(pipeline,'complete',fake_complete)
    async def case():
        assert await MemoryWorker(store).run_once()==1
        assert await MemoryWorker(SessionStorage(tmp_path)).run_once()==0
    asyncio.run(case())
    rows=repo.list_memories(1,MemoryQuery(),tmp_path)['item']
    assert len(calls)==2 and len(rows)==1 and rows[0]['source']=='automatic'
    assert repo.list_memories(2,MemoryQuery(),tmp_path)['total']==0
    with repo.connection(1,tmp_path) as db:
        assert db.execute('SELECT status FROM memory_jobs').fetchone()[0]=='done'
        assert db.execute('SELECT COUNT(*) FROM memory_inputs').fetchone()[0]==2
        assert 'content' not in {row[1] for row in db.execute('PRAGMA table_info(memory_jobs)')}
        assert db.execute('SELECT thread_id FROM memory_origins').fetchone()[0]=='memory-thread'


def test_pref_switch_does_not_change_reading_and_inflight_rejected(tmp_path):
    state=fixture_state();job=jobs.prepare(1,state,tmp_path)
    prefs=repo.preferences(1,MemoryPreference(auto_generate=False,expected_revision=1),tmp_path)
    assert prefs['enabled'] and not prefs['auto_generate']
    assert not jobs.commit(1,job,state,[candidate()],[{'candidate':0,'action':'add'}],[],tmp_path)
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['total']==0
    jobs.fail(1,job,'INPUT_CHANGED',tmp_path,True)
    assert jobs.prepare(1,state,tmp_path) is None


def test_changed_chat_or_manual_edit_discards_generated_result(tmp_path):
    state=fixture_state();job=jobs.prepare(1,state,tmp_path)
    newer=copy.deepcopy(state);newer['nodes']['u1']['content']='不同的内容'
    assert not jobs.commit(1,job,newer,[candidate()],[{'candidate':0,'action':'add'}],[],tmp_path)
    repo.save(1,MemoryWrite(title='手动约定',content='优先保留用户编辑'),root=tmp_path)
    assert not jobs.commit(1,job,state,[candidate()],[{'candidate':0,'action':'add'}],[],tmp_path)
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['total']==1


def test_forget_blocks_old_inputs_and_same_fact(tmp_path):
    state=fixture_state();job=jobs.prepare(1,state,tmp_path)
    assert jobs.commit(1,job,state,[candidate()],[{'candidate':0,'action':'add'}],[],tmp_path)
    row=repo.list_memories(1,MemoryQuery(),tmp_path)['item'][0]
    repo.remove(1,row['id'],row['revision'],tmp_path)
    # 即使旧会话换分支，也不会补提取删除之前的消息。
    state['thread']['updated_at']=datetime.now(timezone.utc).isoformat()
    state['nodes']['u1']['content']+='补充旧记录'
    second=jobs.prepare(1,state,tmp_path)
    assert second['snapshot']['messages']==[]
    assert jobs.commit(1,second,state,[candidate(title='另一种标题')],[{'candidate':0,'action':'add'}],[],tmp_path)
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['total']==0


def test_manual_memory_never_auto_overwritten_and_revisions_retained(tmp_path):
    state=fixture_state()
    manual=repo.save(1,MemoryWrite(title='代码注释习惯',content='手动维护'),root=tmp_path)
    job=jobs.prepare(1,state,tmp_path)
    decision={'candidate':0,'action':'update','target_id':manual['id'],'content':'不允许覆盖'}
    assert jobs.commit(1,job,state,[candidate()],[decision],[manual],tmp_path)
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['item'][0]['content']=='手动维护'


def test_auto_update_preserves_origin_and_history(tmp_path):
    state=fixture_state();job=jobs.prepare(1,state,tmp_path)
    jobs.commit(1,job,state,[candidate()],[{'candidate':0,'action':'add'}],[],tmp_path)
    row=repo.list_memories(1,MemoryQuery(),tmp_path)['item'][0]
    state['nodes']['u1']['content']+='只在必要时说明约束'
    job=jobs.prepare(1,state,tmp_path)
    assert jobs.commit(1,job,state,[candidate()],[{'candidate':0,'action':'update','target_id':row['id'],'content':'注释简洁，必要时说明约束。'}],[row],tmp_path)
    with repo.connection(1,tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_revisions').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM memory_origins').fetchone()[0]==1
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['item'][0]['revision']==2


def test_invalid_model_evidence_secrets_and_low_confidence_rejected(monkeypatch,tmp_path):
    job=jobs.prepare(1,fixture_state(),tmp_path)
    items=[candidate(evidence=[{'message_id':'u1','quote':'不存在的原文'}]),candidate(confidence=0.5),
           candidate(content='api_key=abcdefghijklmnopqrstuvwxy'),candidate(kind='experience'),candidate(scope='project')]
    async def fake(*args):return json.dumps({'memories':items}),'test'
    monkeypatch.setattr(pipeline,'complete',fake)
    assert asyncio.run(pipeline.extract(job['snapshot'],ModelSettings()))==[]
    assert 'abcdef' not in pipeline.redact('password=abcdef')


def test_failed_job_backoff_max_attempts_and_cancel_release(tmp_path):
    state=fixture_state();job=jobs.prepare(1,state,tmp_path)
    jobs.fail(1,job,'MODEL_TIMEOUT',tmp_path)
    assert jobs.prepare(1,state,tmp_path) is None
    with repo.connection(1,tmp_path,True) as db:
        db.execute('UPDATE memory_jobs SET retry_at=0,attempts=3')
    assert jobs.prepare(1,state,tmp_path) is None
    # 新内容才重置失败上限。
    state['nodes']['u1']['content']+='新约定'
    job=jobs.prepare(1,state,tmp_path);assert job['attempts']==1
    jobs.fail(1,job,'CANCELLED',tmp_path,True)
    with repo.connection(1,tmp_path) as db:
        assert db.execute('SELECT attempts FROM memory_jobs').fetchone()[0]==0


def test_old_schema_migrates_without_losing_switch(tmp_path):
    file=repo.memory_file(1,tmp_path);file.parent.mkdir(parents=True)
    db=sqlite3.connect(file)
    db.executescript('CREATE TABLE preferences(id INTEGER PRIMARY KEY,enabled INTEGER,revision INTEGER);INSERT INTO preferences VALUES(1,0,4);')
    db.close()
    prefs=repo.preferences(1,root=tmp_path)
    assert prefs=={'enabled':False,'auto_generate':True,'revision':4}


def test_worker_cancellation_releases_claim(monkeypatch,tmp_path):
    state=fixture_state();store=SessionStorage(tmp_path);save_state(store,state)
    job=jobs.prepare(1,state,tmp_path)
    async def case():
        entered=asyncio.Event()
        async def wait_for_model(*args):
            entered.set()
            await asyncio.Future()
        monkeypatch.setattr(pipeline,'extract',wait_for_model)
        task=asyncio.create_task(MemoryWorker(store).process(job))
        await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(case())
    with repo.connection(1,tmp_path) as db:
        row=db.execute('SELECT * FROM memory_jobs').fetchone()
        assert row['status']=='retry' and row['lease_until']==0 and row['attempts']==0
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['total']==0


def test_failed_model_output_does_not_leak_or_modify_memories(monkeypatch,tmp_path):
    state=fixture_state();store=SessionStorage(tmp_path);save_state(store,state)
    async def invalid(*args):return 'secret upstream text not JSON','test'
    monkeypatch.setattr(pipeline,'complete',invalid)
    asyncio.run(MemoryWorker(store).run_once())
    with repo.connection(1,tmp_path) as db:
        job=dict(db.execute('SELECT * FROM memory_jobs').fetchone())
        assert job['error_code']=='MEMORY_GENERATION_FAILED' and job['status']=='retry'
        assert 'secret' not in json.dumps(job)
    assert repo.list_memories(1,MemoryQuery(),tmp_path)['total']==0


def test_empty_extraction_avoids_second_model_call(monkeypatch,tmp_path):
    state=fixture_state();store=SessionStorage(tmp_path);save_state(store,state)
    calls=[]
    async def empty(*args):calls.append(1);return '{"memories":[]}','test'
    monkeypatch.setattr(pipeline,'complete',empty)
    asyncio.run(MemoryWorker(store).run_once())
    assert calls==[1]
    assert jobs.prepare(1,state,tmp_path) is None
