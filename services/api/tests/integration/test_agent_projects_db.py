"""项目归属、目录切换、审批恢复与移除保留会话。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import delete
from src.infrastructure.database import session
from src.infrastructure.sidecar.context import execution_scope
from src.modules.users import service as users
from src.modules.users.models import User
from src.modules.devices.models import Device
from src.modules.agents import project_service as projects, conversation_service as conversations, approval_service, service as agents
from src.modules.agents.project_schemas import ProjectCreate, ThreadProject
from src.modules.agents.conversation_schemas import ThreadCreate, GraphSave, StoredChat
from src.core.exceptions import ApiError
from tests.integration.test_agent_runs_db import Stream


@asynccontextmanager
async def prepared_project():
    await session.init_db()
    owner = await users.create_user('project-'+uuid4().hex, 'fixture', 'product')
    device = str(uuid4())
    try:
        async with session.transaction() as db:
            db.add(Device(id=device, owner_id=owner.id, session_id=str(uuid4()), lease_until=datetime.now(timezone.utc)+timedelta(minutes=2)))
        body = ProjectCreate(id=str(uuid4()), device_id=device, name='用户项目', path='/user/local/project')
        project = await projects.create(owner.id, body)
        assert await projects.create(owner.id, body) == project
        yield owner, device, project
    finally:
        async with session.transaction() as db: await db.execute(delete(User).where(User.id==owner.id))
        await session.close_db()


def test_project_grouping_and_removal_preserve_history():
    async def case():
        async with prepared_project() as (owner, device, project):
            key='project-thread-'+uuid4().hex
            detail=await conversations.create(owner.id, ThreadCreate(id=key, agent_id=1, project_id=project['id']))
            assert detail['thread']['project_id']==project['id']
            await conversations.create(owner.id, ThreadCreate(id='recent-'+uuid4().hex, agent_id=2))
            rows=await conversations.list_threads(owner.id)
            assert len(rows)==2 and sum(row['project_id']==project['id'] for row in rows)==1
            detail=await conversations.save_graph(owner.id,key,GraphSave(expected_revision=0,messages=[{'id':'u','role':'user','content':'保留历史','created_at':datetime.now(timezone.utc).isoformat()}]))
            assert await projects.list_projects(owner.id+999999)==[]
            with pytest.raises(ApiError): await projects.rename(owner.id+999999,project['id'],'越权')
            renamed=await projects.rename(owner.id,project['id'],'新项目名')
            assert renamed['name']=='新项目名'
            await projects.remove(owner.id,project['id'])
            restored=await conversations.get(owner.id,key)
            assert restored['thread']['project_id'] is None
            assert restored['messages'][0]['content']=='保留历史'
            assert len(await conversations.list_threads(owner.id))==2
    asyncio.run(case())


def test_switch_project_is_versioned_and_owner_scoped():
    async def case():
        async with prepared_project() as (owner, device, project):
            key='thread-'+uuid4().hex
            await conversations.create(owner.id,ThreadCreate(id=key,agent_id=1))
            with pytest.raises(ApiError):
                await projects.set_thread_project(owner.id,key,ThreadProject(project_id=str(uuid4()),expected_revision=0))
            linked=await projects.set_thread_project(owner.id,key,ThreadProject(project_id=project['id'],expected_revision=0))
            assert linked['thread']['project_id']==project['id']
            assert linked['thread']['draft_revision']==1
            with pytest.raises(ApiError):
                await projects.set_thread_project(owner.id,key,ThreadProject(project_id=None,expected_revision=0))
            unlinked=await projects.set_thread_project(owner.id,key,ThreadProject(project_id=None,expected_revision=1))
            assert unlinked['thread']['project_id'] is None
    asyncio.run(case())


def test_approval_keeps_original_project_and_prevents_switching(monkeypatch):
    interrupts=[{'id':'one','value':{'action_requests':[{'name':'write_file','args':{'file_path':'result.md','content':'checked'}}]}}]
    async def case():
        async with prepared_project() as (owner, device, project):
            key='thread-'+uuid4().hex
            await conversations.create(owner.id,ThreadCreate(id=key,agent_id=1,project_id=project['id']))
            saved=await conversations.save_graph(owner.id,key,GraphSave(expected_revision=0,messages=[
                {'id':'u','role':'user','content':'创建文件','created_at':datetime.now(timezone.utc).isoformat()},
                {'id':'a','role':'assistant','content':'','status':'streaming','created_at':datetime.now(timezone.utc).isoformat()}]))
            upstream=AsyncMock(return_value=Stream([{'type':'approval','interrupts':interrupts}]))
            monkeypatch.setattr(agents,'open_chat',upstream)
            body=StoredChat(thread_id=key,response_id='a',expected_revision=saved['thread']['draft_revision'],messages=[{'role':'user','content':'创建文件'}],project_id=str(uuid4()))
            with execution_scope(owner.id,device): stream=await conversations.open_chat(owner.id,key,body)
            assert upstream.call_args.args[0].project_id==project['id']
            async for _ in stream.chunks():pass
            detail=await conversations.get(owner.id,key)
            with pytest.raises(ApiError): await projects.set_thread_project(owner.id,key,ThreadProject(project_id=None,expected_revision=detail['thread']['draft_revision']))
            with pytest.raises(ApiError): await projects.remove(owner.id,project['id'])
            approval=(await approval_service.list_approvals(owner.id,key))[0]
            resumed=AsyncMock(return_value=Stream([{'type':'done','content':'完成'}]));monkeypatch.setattr(agents,'open_chat',resumed)
            next_stream=await approval_service.decide(owner.id,approval['id'],'approve')
            assert resumed.call_args.args[0].project_id==project['id']
            async for _ in next_stream.chunks():pass
    asyncio.run(case())
