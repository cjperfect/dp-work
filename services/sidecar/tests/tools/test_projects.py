"""项目目录必须由本机授权；文件和命令使用项目目录，技能仍按 Agent 隔离。"""
import asyncio
import json
from uuid import uuid4
import pytest
from src import config
from src.tools.workspace import agent_backend
from src.tools.projects import project_workspace
from src.providers.llm.schemas import ModelError


@pytest.fixture
def grant(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path/'workspace')
    project = tmp_path/'user-project'; project.mkdir()
    key = str(uuid4())
    data = tmp_path/'data'; data.mkdir()
    (data/'projects.json').write_text(json.dumps({'projects': {key: {'owner_id': 1, 'path': str(project.resolve()), 'device_id': 'fixture'}}}))
    return key, project


def test_project_backend_uses_folder_and_preserves_agent_skills(grant):
    key, folder = grant
    skills = config.WORKSPACE_DIR/'general/skills/demo'
    skills.mkdir(parents=True)
    (skills/'SKILL.md').write_text('agent skill')
    backend = agent_backend('general', key, 1)
    async def case():
        assert not (await backend.awrite('/report.md', 'project data')).error
        assert (folder/'report.md').read_text() == 'project data'
        assert not (config.WORKSPACE_DIR/'general/report.md').exists()
        assert 'agent skill' in str(await backend.aread('/__agent_skills__/demo/SKILL.md'))
        result = await backend.aexecute('pwd')
        assert str(folder.resolve()) in result.output
    asyncio.run(case())
    assert not (folder/'skills').exists()


def test_unregistered_or_other_account_project_is_rejected(grant):
    key, folder = grant
    assert project_workspace(key, 1) == folder.resolve()
    for invalid_key, owner in [(key, 2), (str(uuid4()), 1), ('../../escape', 1)]:
        with pytest.raises(ModelError): project_workspace(invalid_key, owner)
    folder.rmdir()
    with pytest.raises(ModelError): project_workspace(key, 1)


def test_physical_project_paths_do_not_create_nested_directories(grant):
    key, folder = grant
    folder = folder.resolve()
    backend = agent_backend('general', key, 1)
    physical = str(folder / 'a.txt')
    assert backend.write(physical, '123').error is None
    assert (folder / 'a.txt').read_text() == '123'
    assert not (folder / physical.lstrip('/')).exists()
    assert backend.edit(physical, '123', '456').error is None
    assert '456' in str(backend.read('/a.txt').file_data)
    assert backend.grep('456', str(folder)).matches
    assert backend.ls(str(folder)).entries
    with pytest.raises(ValueError):
        backend.write(str(folder / '../escape.txt'), 'no')
    outside = folder.parent / 'private.txt'
    outside.write_text('private')
    (folder / 'link.txt').symlink_to(outside)
    with pytest.raises(ValueError):
        backend.write(str(folder / 'link.txt'), 'no')
    assert outside.read_text() == 'private'


def test_agent_approval_executes_in_project_and_reads_managed_skills(grant, monkeypatch):
    from tests.agents.test_approvals import Model, input_body, answers
    from langchain_core.messages import AIMessage
    from src.agents import agent
    from src.providers.llm.schemas import ModelSettings
    key, folder = grant
    skills = config.WORKSPACE_DIR/'general/skills/demo'
    skills.mkdir(parents=True)
    (skills/'SKILL.md').write_text('---\nname: demo\ndescription: Project skill test\n---\nMANAGED_SKILL_BODY')
    model = Model(responses=[
        AIMessage('',tool_calls=[{'name':'read_file','args':{'file_path':'/__agent_skills__/demo/SKILL.md'},'id':'skill','type':'tool_call'}]),
        AIMessage('',tool_calls=[{'name':'write_file','args':{'file_path':'.env.approved','content':'inside project'},'id':'write','type':'tool_call'}]),
        AIMessage('完成')])
    monkeypatch.setattr(agent,'create_model',lambda *_:model)
    async def case():
        body = input_body(project_id=key, workspace_owner_id=1)
        events = [event async for event in agent.run_agent(body,ModelSettings(timeout=10))]
        assert events[-1]['type']=='approval',events
        assert not (folder/'.env.approved').exists()
        resumed = body.model_copy(update={'approval_resume':answers(events[-1],'approve')})
        events = [event async for event in agent.run_agent(resumed,ModelSettings(timeout=10))]
        assert events[-1]['type']=='done',events
        assert (folder/'.env.approved').read_text()=='inside project'
        assert not (folder/'skills').exists()
        assert not (config.WORKSPACE_DIR/'general/approved.md').exists()
    asyncio.run(case())
