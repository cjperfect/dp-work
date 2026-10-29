"""本地项目登记必须基于原生授权，删除保留目录和会话。"""
import asyncio
import json
from uuid import uuid4

import pytest
from src import config
from src.sessions import projects, service
from src.sessions.storage import SessionStorage, SessionError


def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    store=SessionStorage(tmp_path)
    monkeypatch.setattr(projects,'storage',store)
    monkeypatch.setattr(service,'storage',store)
    directory=tmp_path/'user-project'
    directory.mkdir()
    (directory/'keep.txt').write_text('keep')
    device,key=str(uuid4()),str(uuid4())
    row={'id':key,'name':'原始目录名','path':str(directory.resolve()),'device_id':device,'owner_id':7}
    (tmp_path/'data').mkdir(exist_ok=True)
    (tmp_path/'data/projects.json').write_text(json.dumps({'projects':{key:row}}))
    return store,directory,device,row


def test_project_registration_requires_grant_and_is_owner_device_scoped(monkeypatch,tmp_path):
    store,directory,device,row=setup(monkeypatch,tmp_path)
    body={k:v for k,v in row.items() if k!='owner_id'}
    created=projects.operation('create',7,body,device)
    assert projects.operation('create',7,body,device)==created
    assert projects.operation('list',8,{},device)==[]
    for bad in ({**body,'path':str(tmp_path)},{**body,'id':str(uuid4())},{**body,'device_id':str(uuid4())}):
        with pytest.raises(SessionError):projects.operation('create',7,bad,device)
    with pytest.raises(SessionError):projects.operation('create',8,body,device)
    with pytest.raises(SessionError):projects.get(7,body['id'],str(uuid4()))
    assert projects.operation('rename',7,{'id':body['id'],'name':'自定义项目'},device)['name']=='自定义项目'
    assert projects.get(7,body['id'],device)['name']=='自定义项目'
    assert len(projects.operation('list',7,{},device))==1


def test_remove_detaches_history_preserves_files_and_can_add_again(monkeypatch,tmp_path):
    store,directory,device,row=setup(monkeypatch,tmp_path)
    projects.operation('create',7,{k:v for k,v in row.items() if k!='owner_id'},device)
    async def case():
        detail=await service.operation('create',{'owner_id':7,'body':{'id':'project-thread','agent_id':1,'project_id':row['id']}})
        assert detail['thread']['project_id']==row['id']
        projects.operation('delete',7,{'id':row['id']},device)
        assert projects.operation('list',7,{},device)==[]
        restored=await service.operation('get',{'owner_id':7,'thread_id':'project-thread'})
        assert restored['thread']['project_id'] is None
        assert (directory/'keep.txt').read_text()=='keep'
        with pytest.raises(SessionError):
            await service.operation('create',{'owner_id':7,'body':{'id':'forged-thread','agent_id':1,'project_id':row['id']}})
        recreated=projects.operation('create',7,{k:v for k,v in row.items() if k!='owner_id'},device)
        assert recreated['id']==row['id']
    asyncio.run(case())


def test_active_run_blocks_removal_before_any_thread_is_detached(monkeypatch,tmp_path):
    store,directory,device,row=setup(monkeypatch,tmp_path)
    projects.operation('create',7,{k:v for k,v in row.items() if k!='owner_id'},device)
    def make(state):
        state.update(service.new_state({'id':'running-thread','agent_id':1,'project_id':row['id']}))
        state['run_id']='running'
        state['runs']['running']={'id':'running','status':'running'}
    # storage 投影需要完整运行元数据中的 status；其余仅用于本地锁校验。
    store.mutate(7,'running-thread','started',make)
    with pytest.raises(SessionError,match='正在运行'):
        projects.operation('delete',7,{'id':row['id']},device)
    assert store.get(7,'running-thread')['thread']['project_id']==row['id']
    assert len(projects.operation('list',7,{},device))==1


def test_moved_folder_does_not_break_list_but_blocks_execution(monkeypatch,tmp_path):
    store,directory,device,row=setup(monkeypatch,tmp_path)
    projects.operation('create',7,{k:v for k,v in row.items() if k!='owner_id'},device)
    directory.rename(tmp_path/'moved')
    assert len(projects.operation('list',7,{},device))==1
    with pytest.raises(Exception):projects.get(7,row['id'],device)
