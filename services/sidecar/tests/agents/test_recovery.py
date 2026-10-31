"""真实图节点恢复、工具凭据去重和不确定副作用拦截。"""
import asyncio
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from src import config
from src.agents import agent
from src.harness import recovery
from src.providers.llm.schemas import ModelSettings
from src.transport.handlers import AgentInput


class Model(FakeMessagesListChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', '{}')
    monkeypatch.setattr(config, 'AGENT_RUN_TOKEN_LIMIT', 0)
    monkeypatch.setattr(config, 'AGENT_RUN_COST_LIMIT', '0')


def body():
    return AgentInput(run_id=str(uuid4()), thread_id='recovery', workspace_owner_id=7,
        messages=[{'role':'user','content':'保存文档'}])


@pytest.mark.parametrize('changed', [None, 'prompt', 'file'])
def test_cancel_during_model_resumes_saved_tool_step(monkeypatch, changed):
    async def case():
        reached = asyncio.Event()
        class Slow(Model):
            async def _agenerate(self, *args, **kwargs):
                if self.i == 1:
                    reached.set()
                    await asyncio.Event().wait()
                return await super()._agenerate(*args, **kwargs)
        model = Slow(responses=[AIMessage('', tool_calls=[{'name':'write_file', 'args':{'file_path':'a.txt','content':'once'},'id':'write1','type':'tool_call'}]), AIMessage('unused')])
        monkeypatch.setattr(agent, 'create_model', lambda *_:model)
        request = body()
        settings = ModelSettings(model='test', timeout=10)
        events = []
        async def execute():
            async for item in agent.run_agent(request, settings): events.append(item)
        task = asyncio.create_task(execute())
        await asyncio.wait_for(reached.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        target = config.WORKSPACE_DIR / 'general/a.txt'
        assert target.read_text() == 'once'
        assert recovery.file(request.run_id, '.sqlite3').exists()
        if changed == 'prompt': (config.WORKSPACE_DIR / 'general/AGENT.md').write_text('changed')
        if changed == 'file': target.write_text('user edit')
        monkeypatch.setattr(agent, 'create_model', lambda *_:Model(responses=[AIMessage('恢复完成')]))
        output = [item async for item in agent.run_agent(request.model_copy(update={'checkpoint_resume':True}), settings)]
        if changed:
            assert output[-1]['code'] == ('RECOVERY_CONFIG_CHANGED' if changed == 'prompt' else 'RECOVERY_FILES_CHANGED'), output
            assert recovery.file(request.run_id, '.sqlite3').exists()
        else:
            assert output[-1]['type'] == 'done' and output[-1]['content'] == '恢复完成', output
            assert not any(item['type'] == 'file_change' for item in output)
            assert not recovery.file(request.run_id, '.sqlite3').exists()
        assert target.read_text() == ('user edit' if changed == 'file' else 'once')
    asyncio.run(case())


def test_tool_result_receipt_closes_gap_before_graph_checkpoint(monkeypatch):
    async def case():
        committed = recovery.RecoveryMiddleware.commit
        def crash_after_commit(self, key, result):
            committed(self, key, result)
            raise RuntimeError('crash before checkpoint commit')
        monkeypatch.setattr(recovery.RecoveryMiddleware, 'commit', crash_after_commit)
        model = Model(responses=[AIMessage('', tool_calls=[{'name':'write_file','args':{'file_path':'a.txt','content':'once'},'id':'write1','type':'tool_call'}])])
        monkeypatch.setattr(agent,'create_model',lambda *_:model)
        request = body()
        settings = ModelSettings(model='test',timeout=10)
        initial = [item async for item in agent.run_agent(request, settings)]
        assert initial[-1]['type'] == 'error'
        assert (config.WORKSPACE_DIR / 'general/a.txt').read_text() == 'once'
        monkeypatch.setattr(recovery.RecoveryMiddleware, 'commit', committed)
        monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('已完成')]))
        output = [item async for item in agent.run_agent(request.model_copy(update={'checkpoint_resume':True}), settings)]
        assert output[-1]['type'] == 'done', output
        assert not any(item['type'] == 'file_change' for item in output)
    asyncio.run(case())


def test_unknown_mutation_is_not_replayed(monkeypatch):
    async def case():
        started = asyncio.Event()
        calls = []
        @tool
        async def mutate_file() -> str:
            """模拟不能重放的外部写入。"""
            calls.append('effect')
            started.set()
            await asyncio.Event().wait()
            return 'unused'
        from src.connectors import tools
        monkeypatch.setattr(tools,'business_tools',lambda *_:[mutate_file])
        monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('',tool_calls=[{'name':'mutate_file','args':{},'id':'external1','type':'tool_call'}])]))
        request=body(); settings=ModelSettings(model='test',timeout=10)
        async def execute():
            return [item async for item in agent.run_agent(request,settings)]
        task=asyncio.create_task(execute())
        await asyncio.wait_for(started.wait(),5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        output=[item async for item in agent.run_agent(request.model_copy(update={'checkpoint_resume':True}),settings)]
        assert output[-1]['code']=='RECOVERY_TOOL_UNCERTAIN', output
        assert calls == ['effect']
    asyncio.run(case())


def test_receipts_roundtrip_tool_messages_and_commands():
    middleware=recovery.RecoveryMiddleware(str(uuid4()))
    for index, result in enumerate([ToolMessage('done',tool_call_id='one'), Command(update={'messages':[ToolMessage('done',tool_call_id='two')], 'files':{'a':{'content':['x']}}})]):
        call={'id':str(index),'name':'write_file','args':{'file_path':'a'}}
        assert middleware.claim(call) is None
        middleware.commit(call['id'],result)
        restored=middleware.claim(call)
        assert type(restored) is type(result)
        if isinstance(result, Command):
            assert restored.update == result.update and tuple(restored.goto) == tuple(result.goto)
        else:
            assert restored == result


def test_process_crash_can_resume_from_disk(monkeypatch, tmp_path):
    """真实子进程被强制结束后，用新图读取磁盘检查点。"""
    import subprocess
    import sys
    import time
    script = r'''
import asyncio,sys
from pathlib import Path
from src import config
from src.agents import agent
from src.transport.handlers import AgentInput
from src.providers.llm.schemas import ModelSettings
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
config.DATA_ROOT=Path(sys.argv[1]);config.WORKSPACE_DIR=config.DATA_ROOT/'workspace'
config.AGENT_RUN_TOKEN_LIMIT=0;config.AGENT_RUN_COST_LIMIT='0';config.AGENT_MODEL_PRICES='{}'
class Model(FakeMessagesListChatModel):
    def bind_tools(self,*args,**kwargs):return self
    async def _agenerate(self,*args,**kwargs):
        if self.i == 1:
            (config.DATA_ROOT/'ready').write_text('ready')
            await asyncio.Event().wait()
        return await super()._agenerate(*args,**kwargs)
model=Model(responses=[AIMessage('',tool_calls=[{'name':'write_file','args':{'file_path':'crash.txt','content':'once'},'id':'w1','type':'tool_call'}]),AIMessage('unused')])
agent.create_model=lambda *_:model
async def case():
    body=AgentInput(run_id=sys.argv[2],thread_id='recovery',workspace_owner_id=7,messages=[{'role':'user','content':'保存文档'}])
    async for _ in agent.run_agent(body,ModelSettings(model='test',timeout=30)):pass
asyncio.run(case())
'''
    request=body()
    child=subprocess.Popen([sys.executable,'-c',script,str(tmp_path),request.run_id], stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+8
        while not (tmp_path/'ready').exists() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        assert (tmp_path/'ready').exists(), '测试子进程没有进入模型等待节点'
    finally:
        child.kill()
        child.communicate(timeout=5)
    monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('重启后恢复完成')]))
    async def case():
        return [item async for item in agent.run_agent(request.model_copy(update={'checkpoint_resume':True}), ModelSettings(model='test',timeout=10))]
    output=asyncio.run(case())
    assert output[-1]['type']=='done', output
    assert output[-1]['content']=='重启后恢复完成'
    assert (config.WORKSPACE_DIR/'general/crash.txt').read_text()=='once'


def test_resuming_a_stopped_approval_requires_a_fresh_decision(monkeypatch):
    async def case():
        request=body(); settings=ModelSettings(model='test',timeout=10)
        monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('',tool_calls=[{'name':'write_file','args':{'file_path':'.env.review','content':'approved'},'id':'w1','type':'tool_call'}])]))
        initial=[item async for item in agent.run_agent(request,settings)]
        assert initial[-1]['type']=='approval'
        resumed=[item async for item in agent.run_agent(request.model_copy(update={'checkpoint_resume':True}),settings)]
        assert resumed[-1]['type']=='approval'
        assert not (config.WORKSPACE_DIR/'general/.env.review').exists()
        decisions={item['id']:{'decisions':[{'type':'approve'}]} for item in resumed[-1]['interrupts']}
        monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('已完成')]))
        completed=[item async for item in agent.run_agent(request.model_copy(update={'approval_resume':decisions}),settings)]
        assert completed[-1]['type']=='done', completed
        assert (config.WORKSPACE_DIR/'general/.env.review').read_text()=='approved'
    asyncio.run(case())
