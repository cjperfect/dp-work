"""真实 API / Node Main 桥接，验证跨进程执行、取消和设备离线。"""
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import delete,select
from src.core import config
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.modules.users import service as users
from src.modules.users.models import User
from src.modules.agents.run_models import AgentRun
from src.modules.knowledge.models import KnowledgeBase
from src.modules.devices.models import Device,DeviceCall
from src.infrastructure.sidecar.relay import cipher,notify
from src.infrastructure.tasks.models import TaskOutbox

ROOT=Path(__file__).resolve().parents[4]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def test_live_device_bridge(monkeypatch,tmp_path,migrated_test_database):
    if not shutil.which('pnpm'):pytest.skip('需要 Node / pnpm 验证桌面桥接')
    monkeypatch.setattr(config,'JWT_SECRET','device-fixture-secret-with-at-least-32-bytes')
    async def make_user():
        await session.init_db()
        owner=await users.create_user('device-'+uuid4().hex,'fixture','product')
        await session.close_db();return owner
    owner=asyncio.run(make_user())
    token=create_access_token(owner.id,owner.role,owner.department)
    port=free_port();api=f'http://127.0.0.1:{port}'
    environment={**os.environ,'DATABASE_URL':migrated_test_database,'JWT_SECRET':'device-fixture-secret-with-at-least-32-bytes',
        'SIDECAR_TRANSPORT':'device','BOOTSTRAP_ADMIN_ENABLED':'0','MQ_DISPATCH_ENABLED':'0','ELASTICSEARCH_ENABLED':'0',
        'DP_DATA_DIR':str(tmp_path/'data')}
    log=open(tmp_path/'api.log','w')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','src.main:app','--host','127.0.0.1','--port',str(port)],
        cwd=ROOT/'services/api',env=environment,stdout=log,stderr=log,start_new_session=True)
    node=None
    task_ids=[]
    def sql(coro):return asyncio.run(coro)
    async def row_state(run_id):
        await session.init_db()
        async with session.read_session() as db:run=await db.get(AgentRun,run_id)
        await session.close_db();return run
    try:
        with httpx.Client(base_url=api,timeout=20,trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:pytest.fail('测试 API 启动失败')
            ready=tmp_path/'ready.json';closed=tmp_path/'closed'
            configuration=tmp_path/'client.json'
            configuration.write_text(json.dumps({'api':api,'installation':str(uuid4()),'token':token,'ready':str(ready),'closed':str(closed)}))
            configuration.chmod(0o600)
            node=subprocess.Popen(['pnpm','--filter','@dp-work/desktop','exec','tsx',str(ROOT/'apps/desktop/tests/fixtures/device-client.mts'),str(configuration)],
                cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
            for _ in range(100):
                if ready.exists():break
                time.sleep(.1)
            else:pytest.fail('Main 测试桥接未连接')
            device=json.loads(ready.read_text())['deviceId']
            headers={'Authorization':'Bearer '+token,'X-Device-ID':device}
            response=client.get('/api/agents/models',headers=headers)
            assert response.status_code==200,response.text
            assert response.json()['data']['models'][0]['id']=='fixture-model'
            assert client.get('/api/skills',headers=headers,params={'agent_code':'general'}).json()['data']['items']==[]
            assert client.get('/api/skills/search',headers=headers,params={'q':'fixture'}).json()['data']['items'][0]['name']=='test-skill'
            response=client.post('/api/skills/install',headers=headers,json={'agent_code':'general','source':'acme/repo@test-skill'})
            assert response.status_code==200,response.text
            assert client.get('/api/skills',headers=headers,params={'agent_code':'general'}).json()['data']['items'][0]['name']=='test-skill'
            assert client.get('/api/skills',headers=headers,params={'agent_code':'product'}).json()['data']['items']==[]
            assert client.post('/api/skills/uninstall',headers=headers,json={'agent_code':'general','skill_id':'acme/repo@test-skill'}).status_code==200
            assert client.get('/api/skills',headers=headers,params={'agent_code':'general'}).json()['data']['items']==[]
            # 即使输入记录被伪造成非白名单路径，Main 也不能转发任意本机地址。
            fake_call=str(uuid4())
            async def forged_call():
                await session.init_db()
                async with session.transaction() as db:
                    binding=await db.get(Device,device)
                    db.add(DeviceCall(id=fake_call,owner_id=owner.id,device_id=device,session_id=binding.session_id,
                        method='POST',path='/internal/../../private',query='',content_type='application/json',
                        encrypted_input=cipher().encrypt(b'fixture-sensitive-input'),state='queued',
                        deadline_at=datetime.now(timezone.utc)+timedelta(seconds=10)))
                    await notify(db,'device_requests',{'session_id':binding.session_id})
                await session.close_db()
            sql(forged_call())
            async def forged_state():
                await session.init_db()
                async with session.read_session() as db: result=await db.get(DeviceCall,fake_call)
                await session.close_db();return result
            for _ in range(50):
                if sql(forged_state()).state=='failed':break
                time.sleep(.05)
            assert sql(forged_state()).state=='failed'
            # 执行结束后不能再次读取原输入，即使属于同一账号。
            assert client.get(f'/api/devices/calls/{fake_call}/input',headers=headers).status_code==404

            key='device-thread-'+uuid4().hex
            assert client.post('/api/agents/threads',headers=headers,json={'id':key,'agent_id':1}).status_code==200
            def prepare(question,revision):
                now=datetime.now(timezone.utc).isoformat()
                return client.put(f'/api/agents/threads/{key}/messages',headers=headers,json={'expected_revision':revision,'messages':[
                    {'id':'u-'+str(revision),'role':'user','content':question,'created_at':now},
                    {'id':'a-'+str(revision),'role':'assistant','content':'','status':'streaming','created_at':now}]}).json()['data']
            detail=prepare('hello',0)
            body={'thread_id':key,'response_id':'a-0','expected_revision':detail['thread']['draft_revision'],
                  'messages':[{'role':'user','content':'hello'}]}
            response=client.post(f'/api/agents/threads/{key}/chat',headers=headers,json=body)
            assert response.status_code==200,response.text
            events=[json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
            assert events[-1]['content']=='本地执行测试完成'
            run=sql(row_state(events[-1]['run_id']))
            assert run.status=='completed' and run.device_id==device
            # 取消需要穿过另一个云端请求，最终中止本机 HTTP 流。
            current=client.get(f'/api/agents/threads/{key}',headers=headers).json()['data']
            detail=prepare('stall',current['thread']['draft_revision'])
            body.update(response_id=detail['messages'][-1]['id'],expected_revision=detail['thread']['draft_revision'])
            with client.stream('POST',f'/api/agents/threads/{key}/chat',headers=headers,json=body) as streaming:
                iterator=streaming.iter_lines();run_id=None
                for line in iterator:
                    if line.startswith('data:'):
                        event=json.loads(line[5:]);run_id=event.get('run_id')
                        if event['type']=='delta':break
                assert run_id
                assert client.post(f'/api/agents/runs/{run_id}/cancel',headers=headers).json()['data']['status']=='cancelled'
                assert 'RUN_STOPPED' in '\n'.join(iterator)
            assert sql(row_state(run_id)).status=='cancelled'
            # 云端独立 Worker 通过同一设备通道解析文件，不能依赖 WebSocket 所在进程内存。
            base=client.post('/api/knowledge-bases',headers=headers,json={'name':'设备解析测试','description':''}).json()['data']['id']
            document=client.post(f'/api/knowledge-bases/{base}/documents/upload',headers=headers,
                files={'file':('device.md',b'# Cloud uploaded content','text/markdown')}).json()['data']
            docpath=f'/api/knowledge-bases/{base}/documents/'+document['id']
            assert client.post(docpath+'/parse',headers=headers).status_code==200
            async def message_for(document_id):
                await session.init_db()
                async with session.read_session() as db:
                    result=await db.scalar(select(TaskOutbox).where(TaskOutbox.kind=='parse',TaskOutbox.target_id==document_id))
                await session.close_db();return result
            task=sql(message_for(document['id']));task_ids.append(task.id)
            assert task.device_id==device
            def consume_task(task_id):
                script='import asyncio; from src.task_handlers import execute; asyncio.run(execute('+repr(task_id)+', "parse"))'
                subprocess.run([sys.executable,'-c',script],cwd=ROOT/'services/api',env=environment,
                    stdout=log,stderr=log,check=True,timeout=20)
            consume_task(task.id)
            assert client.get(docpath,headers=headers).json()['data']['parse_status']=='parsed'
            # 设备离线时数据接口可用，执行接口不会回退到服务器本机。
            os.killpg(node.pid,signal.SIGTERM);node.wait(timeout=5);node=None
            for _ in range(30):
                response=client.get('/api/agents/models',headers=headers)
                if response.status_code==503:break
                time.sleep(.1)
            assert response.status_code==503
            assert client.get('/api/agents/threads',headers=headers).status_code==200
            second='editor-'+uuid4().hex
            second_path=f'/api/knowledge-bases/{base}/documents/'+second
            assert client.put(second_path,headers=headers,json={'title':'离线保留','content':'离线文档'}).status_code==200
            assert client.post(second_path+'/parse',headers=headers).status_code==200
            deferred=sql(message_for(second));task_ids.append(deferred.id)
            consume_task(deferred.id)
            assert client.get(second_path,headers=headers).json()['data']['parse_status']=='queued'
            assert sql(message_for(second)).completed_at is None
            ready.unlink()
            node=subprocess.Popen(['pnpm','--filter','@dp-work/desktop','exec','tsx',str(ROOT/'apps/desktop/tests/fixtures/device-client.mts'),str(configuration)],
                cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
            for _ in range(100):
                if ready.exists():break
                time.sleep(.1)
            else:pytest.fail('设备未重新连接')
            assert json.loads(ready.read_text())['deviceId']==device
            consume_task(deferred.id)
            assert client.get(second_path,headers=headers).json()['data']['parse_status']=='parsed'

    finally:
        if node:
            os.killpg(node.pid,signal.SIGTERM)
            try:node.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(node.pid,signal.SIGKILL);node.wait()
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
        async def cleanup():
            await session.init_db()
            async with session.transaction() as db:
                await db.execute(delete(TaskOutbox).where(TaskOutbox.id.in_(task_ids)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id==owner.id))
                await db.execute(delete(User).where(User.id==owner.id))
            await session.close_db()
        asyncio.run(cleanup())
