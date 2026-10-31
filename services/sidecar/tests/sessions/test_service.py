"""本地会话执行、审批与引导的持久化边界。"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from src.sessions import service
from src.sessions.storage import SessionStorage, SessionError
from src.transport import handlers


def run(case):
    return asyncio.run(case())


def setup(monkeypatch, tmp_path):
    store = SessionStorage(tmp_path)
    monkeypatch.setattr(service, 'storage', store)
    service.ACTIVE.clear()
    return store


async def create_messages():
    key = 'thread1'
    await service.operation('create', {'owner_id':7,'body':{'id':key,'agent_id':1}})
    messages = [
        {'id':'u1','seq':1,'role':'user','content':'写文档','status':'complete','context':{},'created_at':datetime.now(timezone.utc).isoformat()},
        {'id':'a1','seq':2,'role':'assistant','content':'','status':'streaming','context':{},'created_at':datetime.now(timezone.utc).isoformat()}]
    return await service.operation('messages', {'owner_id':7, 'thread_id':key,
        'body':{'expected_revision':0, 'messages':messages}})


def fake_settings(monkeypatch):
    from src.agents import agent
    monkeypatch.setattr(agent, 'settings_for', lambda _: SimpleNamespace(model='test'))


def test_complete_is_local_history_and_tool_events_persist(monkeypatch, tmp_path):
    store = setup(monkeypatch, tmp_path)
    fake_settings(monkeypatch)
    async def fake_chat(params, state):
        async def events():
            yield {'type':'start', 'model':'test'}
            yield {'type':'compaction', 'id':'compact1', 'status':'running'}
            assert store.get(7, 'thread1')['nodes']['a1']['context']['compaction']['status'] == 'running'
            yield {'type':'compaction', 'id':'compact1', 'status':'complete'}
            yield {'type':'reasoning', 'id':'thought1', 'text':'先检查'}
            yield {'type':'reasoning', 'id':'thought1', 'text':'文件'}
            yield {'type':'reasoning_end', 'id':'thought1'}
            yield {'type':'tool_call','id':'call1','name':'read_file','args':{'path':'/a.txt'}}
            yield {'type':'tool_result','id':'call1','content':'文件内容'}
            yield {'type':'file_change', 'change': {'id':'change1', 'path':'/a.txt', 'additions':1, 'deletions':0, 'lines':[{'kind':'added','text':'文件内容'}]}}
            yield {'type':'delta','text':'已完成'}
            yield {'type':'done','content':'已完成','model':'test'}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        detail = await create_messages()
        assert await service.operation('list', {'owner_id':7}) == []
        stream = await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}}, None)
        events = [e async for e in stream.events]
        assert events[-1]['type'] == 'done'
        result = await service.operation('get', {'owner_id':7,'thread_id':'thread1'})
        assert result['messages'][-1]['content'] == '已完成'
        assert result['messages'][-1]['context']['compaction'] == {'id':'compact1', 'status':'complete'}
        thought = result['messages'][-1]['context']['reasoning'][0]
        assert thought['text'] == '先检查文件' and thought['completed_at'] >= thought['started_at']
        assert result['messages'][-1]['context']['execution_order'] == ['reasoning:thought1','tool:call1']
        assert result['messages'][-1]['context']['file_changes'][0]['id'] == 'change1'
        trace = result['messages'][-1]['context']['tool_calls'][0]
        assert trace['id'] == 'call1' and trace['status'] == 'complete'
        assert trace['result'] == '文件内容'
        assert trace['ended_at'] >= trace['started_at']
        assert next(e for e in events if e['type'] == 'tool_call')['trace']['status'] == 'running'
        assert next(e for e in events if e['type'] == 'tool_result')['trace'] == trace
        assert result['thread']['has_history']
        assert len(await service.operation('list', {'owner_id':7})) == 1
        rows = await service.operation('runs.list', {'owner_id':7})
        assert rows['item'][0]['status'] == 'completed'
        assert service.ACTIVE == {}
    run(case)
    text = (store.paths(7)[1]/'thread1.jsonl').read_text()
    assert 'tool_call' in text and '文件内容' in text
    assert 'retrieval_token' not in text


def test_optimistic_revision_and_tombstone_prevent_resurrection(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    async def case():
        detail = await create_messages()
        with pytest.raises(SessionError, match='其他页面'):
            await service.operation('draft', {'owner_id':7,'thread_id':'thread1','body':{
                'expected_revision':0,'draft':'old','knowledge_base_ids':[]}})
        await service.operation('delete', {'owner_id':7,'thread_id':'thread1'})
        with pytest.raises(SessionError, match='不存在'):
            await service.operation('create', {'owner_id':7,'body':{'id':'thread1','agent_id':1}})
        imported = await service.operation('import', {'owner_id':7,'body':detail})
        assert imported is None
    run(case)


def test_approval_decision_single_use_and_resume_same_run(monkeypatch, tmp_path):
    store = setup(monkeypatch, tmp_path)
    fake_settings(monkeypatch)
    calls=[]
    async def fake_chat(params, state):
        calls.append(params)
        async def events():
            yield {'type':'start'}
            if params['approval_resume']:
                yield {'type':'done','content':'允许后完成'}
            else:
                yield {'type':'approval','interrupts':[{'id':'i1','value':{'action_requests':[{'name':'execute','args':{'command':'rm a'}}]}}]}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        detail = await create_messages()
        stream = await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}}, None)
        events=[e async for e in stream.events]
        aid=events[-1]['approval_id']
        assert store.get(7,'thread1')['nodes']['a1']['status']=='waiting_approval'
        resumed=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'approval_id':aid,'decision':'approve'}}, None, resume=True)
        result=[e async for e in resumed.events]
        assert result[-1]['type']=='done'
        assert calls[0]['run_id']==calls[1]['run_id']
        assert calls[1]['approval_resume']['i1']['decisions']==[{'type':'approve'}]
        with pytest.raises(SessionError, match='审批'):
            await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
                'approval_id':aid,'decision':'approve'}}, None, resume=True)
    run(case)


def test_steering_branches_preserve_preceding_tool_context(monkeypatch, tmp_path):
    store = setup(monkeypatch,tmp_path)
    fake_settings(monkeypatch)
    guide_id=str(uuid4())
    async def fake_chat(params,state):
        async def events():
            yield {'type':'delta','text':'先前回答'}
            def queue(s):
                s['steering'][guide_id]={'content':'改成黑色','status':'queued'}
            await service.io(store.mutate,7,'thread1','guide',queue)
            yield {'type':'steering','id':guide_id}
            yield {'type':'done','content':'改好了'}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers,'agent_chat',fake_chat)
    async def case():
        detail=await create_messages()
        stream=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}},None)
        events=[e async for e in stream.events]
        applied=next(e for e in events if e['type']=='steering')
        assert applied['previous_content']=='先前回答'
        assert applied['message']['context']['steering_status']=='applied'
        detail=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        assert [m['content'] for m in detail['messages']]==['写文档','先前回答','改成黑色','改好了']
    run(case)


def test_pg_import_preserves_project_and_is_idempotent(monkeypatch,tmp_path):
    store=setup(monkeypatch,tmp_path)
    async def case():
        original=await create_messages()
        original['thread']['id']='imported'
        original['project_id']=str(uuid4())
        original['messages'][-1].update(content='旧历史',status='complete')
        original['message_branches']=[]
        imported=await service.operation('import',{'owner_id':7,'body':original})
        assert imported['thread']['project_id']==original['project_id']
        assert imported['messages'][-1]['content']=='旧历史'
        await service.operation('rename',{'owner_id':7,'thread_id':'imported','body':{'title':'本地标题'}})
        duplicate=await service.operation('import',{'owner_id':7,'body':original})
        assert duplicate['thread']['title']=='本地标题'
        assert duplicate['messages']==imported['messages']
    run(case)


def test_cancel_stops_active_execution_and_preserves_partial_reply(monkeypatch,tmp_path):
    store=setup(monkeypatch,tmp_path)
    fake_settings(monkeypatch)
    stopped=[]
    async def case():
        detail=await create_messages()
        started=asyncio.Event()
        async def fake_chat(params,state):
            async def events():
                try:
                    yield {'type':'delta','text':'已生成部分'}
                    started.set()
                    await asyncio.Event().wait()
                finally:
                    stopped.append(True)
            return handlers.EventStream(events())
        monkeypatch.setattr(handlers,'agent_chat',fake_chat)
        async def collect():
            stream=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
                'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}},None)
            return [e async for e in stream.events]
        task=asyncio.create_task(collect())
        await asyncio.wait_for(started.wait(),3)
        listing=await service.operation('runs.list',{'owner_id':7,'body':{'conversation_id':'thread1'}})
        result=await service.operation('runs.cancel',{'owner_id':7,'body':{'run_id':listing['item'][0]['id']}})
        assert result['status']=='cancelled'
        with pytest.raises(asyncio.CancelledError):
            await task
        saved=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        assert saved['messages'][-1]['status']=='cancelled'
        assert saved['messages'][-1]['content']=='已生成部分'
        assert stopped==[True]
    run(case)


def test_image_references_persist_while_model_gets_actual_image(monkeypatch, tmp_path):
    import base64
    from src.sessions import images
    store = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(images, 'storage', store)
    fake_settings(monkeypatch)
    url = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
    ref = images.save(7, {'name':'截图.png', 'content_type':'image/png', 'data_url':url})
    async def fake_chat(params, state):
        assert params['messages'][-1]['images'] == [url]
        async def events():
            yield {'type':'done','content':'已查看图片'}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        detail = await create_messages()
        detail['messages'][0]['context']['images'] = [ref]
        saved = await service.operation('messages', {'owner_id':7,'thread_id':'thread1','body':{
            'expected_revision':detail['thread']['draft_revision'],'messages':detail['messages']}})
        stream = await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','expected_revision':saved['thread']['draft_revision'],'response_id':'a1'}}, None)
        events = [event async for event in stream.events]
        assert events[-1]['type'] == 'done'
        result = await service.operation('get', {'owner_id':7,'thread_id':'thread1'})
        assert result['messages'][0]['context']['images'] == [ref]
    run(case)
    assert url not in (store.paths(7)[1]/'thread1.jsonl').read_text()


def test_stopping_during_reasoning_flushes_last_unsaved_text(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    fake_settings(monkeypatch)
    async def fake_chat(params,state):
        async def events():
            yield {'type':'reasoning','id':'r1','text':'尚未写入定时批次的思考'}
            await asyncio.sleep(60)
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers,'agent_chat',fake_chat)
    async def case():
        detail=await create_messages()
        stream=await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}},None)
        event=await anext(stream.events)
        assert event['type']=='reasoning'
        await stream.events.aclose()
        result=await service.operation('get',{'owner_id':7,'thread_id':'thread1'})
        thought=result['messages'][-1]['context']['reasoning'][0]
        assert thought['text']=='尚未写入定时批次的思考'
        assert thought['completed_at'] >= thought['started_at']
        assert result['messages'][-1]['status']=='cancelled'
    run(case)


def test_curated_memory_loaded_without_copying_messages(monkeypatch, tmp_path):
    from src.memory import repository as memory
    from src.memory.schemas import MemoryWrite, MemoryQuery
    store = setup(monkeypatch, tmp_path)
    fake_settings(monkeypatch)
    from src.memory import vectors
    queries = []
    class Embeddings:
        async def aembed_documents(self, texts):
            return [[1., 0.] for _ in texts]
        async def aembed_query(self, text):
            queries.append(text)
            return [1., 0.]
    monkeypatch.setattr(vectors, 'ArkEmbeddings', Embeddings)
    row = memory.save(7, MemoryWrite(title='回答风格', content='使用简短中文'), root=tmp_path)
    captured = []
    async def fake_chat(params, state):
        captured.append(params)
        async def events():
            yield {'type': 'start', 'model': 'test'}
            yield {'type': 'done', 'content': '已完成', 'model': 'test'}
        return handlers.EventStream(events())
    monkeypatch.setattr(handlers, 'agent_chat', fake_chat)
    async def case():
        detail = await create_messages()
        stream = await service.open_chat({'owner_id':7,'thread_id':'thread1','body':{
            'thread_id':'thread1','expected_revision':detail['thread']['draft_revision'],'response_id':'a1'}}, None)
        _ = [e async for e in stream.events]
        assert queries == [next(row['content'] for row in reversed(captured[0]['messages']) if row['role'] == 'user')]
        assert '使用简短中文' in captured[0]['memory_context']
        stored = store.get(7, 'thread1')
        assert stored['nodes']['a1']['context']['memory_sources'][0]['id'] == row['id']
        assert memory.list_memories(7, MemoryQuery(), tmp_path)['total'] == 1
    run(case)
