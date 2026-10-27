"""会话持久化、权限、版本、分支和 SSE 保存。"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from src.core.exceptions import ApiError
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.agents import conversation_service as conversations, service as agents
from src.modules.agents.conversation_models import Conversation, ConversationMessage
from src.modules.agents.conversation_schemas import ThreadCreate, GraphSave, DraftSave, ImportThread, RenameThread, StoredChat
from src.modules.users import service as users
from src.modules.users.models import User


def message(key, role='user', text='原问题', status='complete'):
    return {'id': key, 'role': role, 'content': text, 'status': status, 'seq': 0,
        'created_at': datetime.now(timezone.utc).isoformat(), 'context': {'agent': {'id': 1}}}


def test_conversation_api_permissions_revision_import_and_delete():
    async def case():
        await session.init_db()
        owners = [await users.create_user('conversation-' + uuid4().hex, 'fixture', 'product') for _ in range(2)]
        key = 'thread-' + uuid4().hex
        try:
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test') as client:
                headers = {'Authorization': 'Bearer ' + create_access_token(owners[0].id, owners[0].role, owners[0].department)}
                other = {'Authorization': 'Bearer ' + create_access_token(owners[1].id, owners[1].role, owners[1].department)}
                root = '/api/agents/threads'; path = root + '/' + key
                assert (await client.get(root)).status_code == 401
                response = await client.post(root, headers=headers, json={'id': key, 'agent_id': 1})
                assert response.status_code == 200, response.text
                first = response.json()['data']
                assert (await client.post(root, headers=headers, json={'id': key, 'agent_id': 1})).json()['data'] == first
                for method, endpoint, data in [('GET',path,None), ('DELETE',path,None), ('PATCH',path,{'title':'越权'}),
                    ('POST',root,{'id':key,'agent_id':1})]:
                    assert (await client.request(method,endpoint,headers=other,json=data)).status_code == 404
                saved = await client.patch(path+'/draft', headers=headers, json={'expected_revision':0,'draft':'草稿','knowledge_base_ids':[]})
                assert saved.status_code == 200
                assert (await client.patch(path+'/draft', headers=headers, json={'expected_revision':0,'draft':'旧页面','knowledge_base_ids':[]})).status_code == 409
                original, reply = message('u'), message('a','assistant','原答案')
                graph = {'expected_revision':1, 'messages':[original,reply]}
                response = await client.put(path+'/messages', headers=headers, json=graph)
                assert response.status_code == 200, response.text
                original_detail = response.json()['data']
                edited, second = message('u2',text='新问题'), message('a2','assistant','新答案')
                response = await client.put(path+'/messages', headers=headers,json={'expected_revision':2,'messages':[edited,second],
                    'message_branches':original_detail['message_branches']})
                assert response.status_code == 200, response.text
                current=response.json()['data']
                assert len(current['message_branches']) == 4 and current['messages'][0]['content'] == '新问题'
                response=await client.put(path+'/messages',headers=headers,json={'expected_revision':3,'messages':[original,reply], 'message_branches':current['message_branches']})
                assert response.status_code == 200
                # 数据库重连后分支、草稿和选中路径仍完整。
                await session.close_db(); await session.init_db()
                current=(await client.get(path,headers=headers)).json()['data']
                assert len(current['message_branches']) == 4 and current['messages'][0]['content']=='原问题'
                assert current['thread']['draft']=='草稿'
                await client.patch(path,headers=headers,json={'title':'人工标题'})
                await client.patch(path,headers=headers,json={'title':'延迟标题','title_source':'generated','first_message_id':'u'})
                assert (await client.get(path,headers=headers)).json()['data']['thread']['title']=='人工标题'
                assert len((await client.get(root,headers=headers,params={'q':'人工'})).json()['data']) == 1
                assert not (await client.get(root,headers=other)).json()['data']
                imported={**current,'thread':{**current['thread'],'title':'不应覆盖'}}
                assert (await client.post(root+'/import',headers=headers,json=imported)).json()['data']['thread']['title']=='人工标题'
                assert (await client.delete(path,headers=headers)).status_code==200
                assert (await client.get(path,headers=headers)).status_code==404
                assert (await client.put(path+'/messages',headers=headers,json=graph)).status_code==404
                assert (await client.post(root+'/import',headers=headers,json=imported)).json()['data'] is None
                async with session.read_session() as db:
                    assert not (await db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id==key))).all()
        finally:
            async with session.transaction() as db:
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())


def test_stream_uses_pg_history_saves_before_done_and_preserves_cancelled_text(monkeypatch):
    class Stream:
        closed = False
        async def close(self): self.closed = True
        async def chunks(self):
            yield 'data: {"type":"delta","text":"部分回答"}\n\n'.encode()
            yield 'data: {"type":"done","content":"最终回答"}\n\n'.encode()
    upstream = Stream()
    model = AsyncMock(return_value=upstream)
    monkeypatch.setattr(agents,'open_chat',model)
    async def case():
        await session.init_db()
        owner=await users.create_user('stream-store-'+uuid4().hex,'fixture','product')
        key='thread-'+uuid4().hex
        try:
            await conversations.create(owner.id,ThreadCreate(id=key,agent_id=1))
            prepared=await conversations.save_graph(owner.id,key,GraphSave(expected_revision=0,messages=[
                message('u',text='PG 中的问题'),message('a','assistant','',status='streaming')]))
            body=StoredChat(agent_code='product',thread_id=key,response_id='a',expected_revision=prepared['thread']['draft_revision'],
                messages=[{'role':'user','content':'伪造的历史'}])
            stream=await conversations.open_chat(owner.id,key,body)
            assert model.call_args.args[0].agent_code=='general'
            assert model.call_args.args[0].messages[0].content=='PG 中的问题'
            with pytest.raises(ApiError):
                await conversations.save_draft(owner.id,key,DraftSave(expected_revision=1,draft='并发覆盖'))
            async for frame in stream.chunks():
                if '"type":"done"' in frame.decode():
                    saved=await conversations.get(owner.id,key)
                    assert saved['messages'][-1]['content']=='最终回答' and saved['messages'][-1]['status']=='complete'
            assert upstream.closed
            # 重复执行已完成的 assistant 不得再次调用模型。
            with pytest.raises(ApiError): await conversations.open_chat(owner.id,key,body)
            saved=await conversations.get(owner.id,key)
            prepared=await conversations.save_graph(owner.id,key,GraphSave(expected_revision=saved['thread']['draft_revision'],messages=[
                *saved['messages'],message('u2',text='下一问'),message('a2','assistant','',status='streaming')]))
            stream=await conversations.open_chat(owner.id,key,StoredChat(thread_id=key,response_id='a2',expected_revision=prepared['thread']['draft_revision'],messages=[{'role':'user','content':'忽略'}]))
            iterator=stream.chunks(); await anext(iterator); await iterator.aclose()
            saved=await conversations.get(owner.id,key)
            assert saved['messages'][-1]['content']=='部分回答' and saved['messages'][-1]['status']=='cancelled'
        finally:
            async with session.transaction() as db: await db.execute(delete(User).where(User.id==owner.id))
            await session.close_db()
    asyncio.run(case())


def test_invalid_graph_is_rejected():
    with pytest.raises(ValueError):
        GraphSave(expected_revision=0,message_branches=[{'parentId':'u','message':message('u')}])
    with pytest.raises(ValueError):
        GraphSave(expected_revision=0,messages=[message('u'),message('u')])
