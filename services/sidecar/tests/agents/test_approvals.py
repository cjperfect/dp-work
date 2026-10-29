"""真实图中断与磁盘检查点恢复，不调用付费模型。"""
import asyncio
import shlex
import sys
from uuid import uuid4
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from src import config
from src.agents import agent
from src.providers.llm.schemas import ModelSettings
from src.transport.handlers import AgentInput
from src.tools.isolation import sandbox_backend


class Model(FakeMessagesListChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def input_body(**kwargs):
    return AgentInput(run_id=str(uuid4()), thread_id='approval-test', messages=[{'role': 'user', 'content': '保存文档'}], **kwargs)


def answers(event, decision):
    return {item['id']: {'decisions': [{'type': decision} for _ in item['value']['action_requests']]}
            for item in event['interrupts']}


@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_durable_pause_and_single_decision(monkeypatch, tmp_path, decision):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    model = Model(responses=[AIMessage('', tool_calls=[{'name': 'write_file', 'args': {'file_path': '.env.reviewed', 'content': 'after approval'}, 'id': 'write', 'type': 'tool_call'}]), AIMessage('已处理')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        initial = [item async for item in agent.run_agent(body, ModelSettings(timeout=10))]
        pending = initial[-1]
        assert pending['type'] == 'approval'
        assert not any(item['type'] == 'file_change' for item in initial)
        assert not (config.WORKSPACE_DIR / 'general/.env.reviewed').exists()
        assert list((tmp_path / 'data/agent-checkpoints').glob('*.sqlite3'))
        # 新模型实例和新图从磁盘恢复，相当于 Sidecar 重启。
        monkeypatch.setattr(agent, 'create_model', lambda *_: Model(responses=[AIMessage('已处理')]))
        resumed = body.model_copy(update={'approval_resume': answers(pending, decision)})
        completed = [item async for item in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert completed[-1]['type'] == 'done', completed
        assert not list((tmp_path / 'data/agent-checkpoints').glob('*.sqlite3'))
        assert (config.WORKSPACE_DIR / 'general/.env.reviewed').exists() == (decision == 'approve')
        replay = [item async for item in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert replay[-1]['code'] == 'APPROVAL_STALE'
    asyncio.run(case())


def test_subagent_write_also_requires_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    model = Model(responses=[
        AIMessage('', tool_calls=[{'name': 'task', 'args': {'description': '写 .env.delegated', 'subagent_type': 'general-purpose'}, 'id': 'delegate', 'type': 'tool_call'}]),
        AIMessage('', tool_calls=[{'name': 'write_file', 'args': {'file_path': '.env.delegated', 'content': 'child'}, 'id': 'child-write', 'type': 'tool_call'}]),
        AIMessage('子任务完成'), AIMessage('完成')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'approval', events
        assert not (config.WORKSPACE_DIR / 'general/.env.delegated').exists()
        resumed = body.model_copy(update={'approval_resume': answers(events[-1], 'approve')})
        events = [event async for event in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'done', events
        assert (config.WORKSPACE_DIR / 'general/.env.delegated').read_text() == 'child'
    asyncio.run(case())


@pytest.mark.parametrize('tool_name,args,file_name', [
    ('edit_file', {'file_path': '.env.existing', 'old_string': 'before', 'new_string': 'after'}, '.env.existing'),
    ('execute', {'command': 'printf reviewed > shell.md'}, 'shell.md'),
])
@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_edit_and_shell_require_approval(monkeypatch, tmp_path, tool_name, args, file_name, decision):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    folder = config.WORKSPACE_DIR / 'general'
    folder.mkdir(parents=True)
    if tool_name == 'edit_file': (folder / file_name).write_text('before')
    model = Model(responses=[AIMessage('', tool_calls=[{'name': tool_name, 'args': args, 'id': 'tool', 'type': 'tool_call'}]), AIMessage('完成')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'approval', events
        assert not any(item['type'] == 'file_change' for item in events)
        if tool_name == 'edit_file': assert (folder / file_name).read_text() == 'before'
        else: assert not (folder / file_name).exists()
        resumed = body.model_copy(update={'approval_resume': answers(events[-1], decision)})
        result = [event async for event in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert result[-1]['type'] == 'done', result
        if tool_name == 'edit_file': assert (folder / file_name).read_text() == ('after' if decision == 'approve' else 'before')
        else: assert (folder / file_name).exists() == (decision == 'approve')
    asyncio.run(case())


@pytest.mark.skipif(sandbox_backend() not in ('macos', 'linux'), reason='需要本机原生沙箱')
def test_approved_python_still_cannot_write_outside_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    outside = tmp_path / 'outside.txt'
    program = f'from pathlib import Path; Path("inside.txt").write_text("allowed"); Path({str(outside)!r}).write_text("denied")'
    command = shlex.quote(sys.executable) + ' -c ' + shlex.quote(program)
    model = Model(responses=[AIMessage('', tool_calls=[{'name': 'execute', 'args': {'command': command}, 'id': 'script', 'type': 'tool_call'}]), AIMessage('已处理')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'approval'
        inside = config.WORKSPACE_DIR / 'general/inside.txt'
        assert not inside.exists() and not outside.exists()
        resumed = body.model_copy(update={'approval_resume': answers(events[-1], 'approve')})
        completed = [event async for event in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert completed[-1]['type'] == 'done', completed
        assert inside.read_text() == 'allowed'
        assert not outside.exists()
    asyncio.run(case())


def test_batch_decision_must_match_all_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    calls = [{'name': 'write_file', 'args': {'file_path': '.env.'+name, 'content': name}, 'id': name, 'type':'tool_call'} for name in ('one','two')]
    model = Model(responses=[AIMessage('', tool_calls=calls), AIMessage('完成')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        pending = events[-1]
        assert pending['type'] == 'approval'
        invalid = answers(pending, 'approve')
        first_key = next(iter(invalid))
        invalid[first_key]['decisions'] = []
        error = [event async for event in agent.run_agent(body.model_copy(update={'approval_resume':invalid}), ModelSettings(timeout=10))]
        assert error[-1]['code'] == 'APPROVAL_INVALID'
        assert not (config.WORKSPACE_DIR/'general/.env.one').exists()
        result = [event async for event in agent.run_agent(body.model_copy(update={'approval_resume':answers(pending,'approve')}), ModelSettings(timeout=10))]
        assert result[-1]['type'] == 'done', result
        assert (config.WORKSPACE_DIR/'general/.env.one').read_text() == 'one'
        assert (config.WORKSPACE_DIR/'general/.env.two').read_text() == 'two'
    asyncio.run(case())


def test_read_file_does_not_require_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    folder = config.WORKSPACE_DIR/'general'
    folder.mkdir(parents=True)
    (folder/'reference.md').write_text('Read-only context')
    model = Model(responses=[AIMessage('', tool_calls=[{'name':'read_file','args':{'file_path':'reference.md'},'id':'read','type':'tool_call'}]), AIMessage('已读取')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        result = [event async for event in agent.run_agent(input_body(), ModelSettings(timeout=10))]
        assert result[-1]['type'] == 'done', result
        assert not any(event['type'] == 'approval' for event in result)
        assert not list((tmp_path/'data/agent-checkpoints').glob('*.sqlite3'))
    asyncio.run(case())

def test_normal_write_edit_and_pwd_run_without_pause_but_deletion_waits(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path/'workspace')
    model = Model(responses=[
        AIMessage('', tool_calls=[{'name':'write_file','args':{'file_path':'a.txt','content':'123'},'id':'write','type':'tool_call'}]),
        AIMessage('', tool_calls=[{'name':'edit_file','args':{'file_path':'a.txt','old_string':'123','new_string':'456'},'id':'edit','type':'tool_call'}]),
        AIMessage('', tool_calls=[{'name':'execute','args':{'command':'pwd && ls -la'},'id':'pwd','type':'tool_call'}]),
        AIMessage('', tool_calls=[{'name':'execute','args':{'command':"wc -c a.txt; head -3 a.txt; echo '---'; tail -2 a.txt"},'id':'verify','type':'tool_call'}]),
        AIMessage('', tool_calls=[{'name':'execute','args':{'command':'rm a.txt'},'id':'delete','type':'tool_call'}]),
        AIMessage('保留文件'),
    ])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        body = input_body()
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'approval', events
        actions = [action for interrupt in events[-1]['interrupts'] for action in interrupt['value']['action_requests']]
        assert [action['args'] for action in actions] == [{'command':'rm a.txt'}]
        assert (tmp_path/'workspace/general/a.txt').read_text() == '456'
        resumed = body.model_copy(update={'approval_resume':answers(events[-1], 'reject')})
        completed = [event async for event in agent.run_agent(resumed, ModelSettings(timeout=10))]
        assert completed[-1]['type'] == 'done', completed
        assert (tmp_path/'workspace/general/a.txt').read_text() == '456'
    asyncio.run(case())
