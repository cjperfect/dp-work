"""停止、重启读取、原任务恢复及账号/会话版本边界。"""
import asyncio
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from src import config
from src.agents import agent
from src.providers.llm.schemas import ModelSettings
from src.sessions import service
from src.sessions.storage import SessionStorage, SessionError, now
from src.harness import recovery


class Model(FakeMessagesListChatModel):
    def bind_tools(self,*args,**kwargs): return self


@pytest.fixture
def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(config,'AGENT_MODEL_PRICES','{}')
    monkeypatch.setattr(config,'AGENT_RUN_TOKEN_LIMIT',0)
    monkeypatch.setattr(config,'AGENT_RUN_COST_LIMIT','0')
    monkeypatch.setattr(service,'storage',SessionStorage(tmp_path))
    monkeypatch.setattr(agent,'settings_for',lambda *_:ModelSettings(model='test',timeout=10))
    from src.transport import handlers
    monkeypatch.setattr(handlers,'settings_for',lambda *_:ModelSettings(model='test',timeout=10))
    from src.memory import service as memory
    async def no_memory(*args): return {'context':'','sources':[]}
    monkeypatch.setattr(memory,'semantic_recall',no_memory)
    service.ACTIVE.clear()
    return tmp_path


async def create():
    await service.operation('create',{'owner_id':7,'body':{'id':'thread1','agent_id':1}})
    return await service.operation('messages',{'owner_id':7,'thread_id':'thread1','body':{
        'expected_revision':0,'messages':[
            {'id':'u','role':'user','content':'写文件再说明','context':{},'created_at':now()},
            {'id':'a','role':'assistant','content':'','status':'streaming','context':{},'created_at':now()}]}})


async def stopped(monkeypatch):
    reached=asyncio.Event()
    class Slow(Model):
        async def _agenerate(self,*args,**kwargs):
            if self.i == 1:
                reached.set()
                await asyncio.Event().wait()
            return await super()._agenerate(*args,**kwargs)
    model=Slow(responses=[AIMessage('文件已保存。',tool_calls=[{'name':'write_file','args':{'file_path':'a.txt','content':'once'},'id':'w1','type':'tool_call'}]),AIMessage('unused')])
    monkeypatch.setattr(agent,'create_model',lambda *_:model)
    detail=await create()
    async def execute():
        stream=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','response_id':'a','expected_revision':detail['thread']['draft_revision']}},None)
        return [event async for event in stream.events]
    task=asyncio.create_task(execute())
    await asyncio.wait_for(reached.wait(),5)
    row=service.storage.get(7,'thread1')
    run=row['runs'][row['run_id']]
    await service.runs('cancel',7,{'conversation_id':'thread1','run_id':run['id']})
    assert task.done()
    return run['id']


def test_stop_reload_and_resume_same_run_without_duplicate_text_or_files(setup,monkeypatch):
    async def case():
        run_id=await stopped(monkeypatch)
        saved=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        assert saved['messages'][-1]['context']['recovery']['run_id']==run_id
        assert recovery.file(run_id,'.usage.json').exists()
        monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('继续完成。')]))
        stream=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'run_id':run_id,'expected_revision':saved['thread']['draft_revision']}},None,resume='checkpoint')
        with pytest.raises(SessionError, match='正在运行'):
            await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{'run_id':run_id,'expected_revision':saved['thread']['draft_revision']}},None,resume='checkpoint')
        events=[event async for event in stream.events]
        assert events[-1]['type']=='done', events
        assert events[-1]['content']=='文件已保存。继续完成。'
        assert next(event for event in events if event['type']=='restore')['content']=='文件已保存。'
        result=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        assert len(result['messages'])==2 and result['messages'][-1]['id']=='a'
        assert result['messages'][-1]['content']=='文件已保存。继续完成。'
        assert 'recovery' not in result['messages'][-1]['context']
        assert list(service.storage.get(7,'thread1')['runs'])==[run_id]
        assert not recovery.file(run_id,'.sqlite3').exists()
        assert not recovery.file(run_id,'.tools.sqlite3').exists()
        assert not recovery.file(run_id,'.usage.json').exists()
        with pytest.raises(SessionError):
            await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{'run_id':run_id,'expected_revision':result['thread']['draft_revision']}},None,resume='checkpoint')
    asyncio.run(case())


def test_changed_branch_revision_and_other_account_cannot_resume(setup,monkeypatch):
    async def case():
        run_id=await stopped(monkeypatch)
        saved=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        with pytest.raises(SessionError):
            await service.operation('resume.lookup',{'owner_id':8,'thread_id':'thread1','body':{'run_id':run_id}})
        with pytest.raises(SessionError,match='其他页面'):
            await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{'run_id':run_id,'expected_revision':0}},None,resume='checkpoint')
        def change(state):state['nodes']['u']['content']='用户已修改原问题'
        service.storage.mutate(7,'thread1','fixture',change)
        with pytest.raises(SessionError,match='会话内容'):
            await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{'run_id':run_id,'expected_revision':saved['thread']['draft_revision']}},None,resume='checkpoint')
        assert service.storage.get(7,'thread1')['run_id'] is None
    asyncio.run(case())


def test_delete_cleans_all_retained_checkpoints(setup,monkeypatch):
    async def case():
        run_id=await stopped(monkeypatch)
        assert recovery.file(run_id,'.sqlite3').exists()
        await service.operation('delete',{'owner_id':7,'thread_id':'thread1'})
        assert not recovery.file(run_id,'.sqlite3').exists()
        assert not recovery.file(run_id,'.recovery.json').exists()
        assert not recovery.file(run_id,'.tools.sqlite3').exists()
    asyncio.run(case())
