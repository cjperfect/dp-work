"""评测链路、失败门禁、隔离及本地模式禁止上传。"""
import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip('langsmith',minversion='0.14.12')

# evals 是仅在开发目录运行的包，不打入桌面安装包。
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from evals.run import evaluate, load_cases, parser, examples, remote_examples
from evals.registry import rules
from evals.agent.targets import Target
from src import config
from src.providers.llm.schemas import ModelSettings
from src.tools import workspace


def test_offline_smoke_never_uploads_and_restores_runtime(monkeypatch,tmp_path):
    import requests
    def forbidden(*args,**kwargs):
        pytest.fail('本地评测不应发送 LangSmith HTTP 请求')
    monkeypatch.setattr(requests.Session,'request',forbidden)
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('LANGSMITH_API_KEY','must-not-leave-this-process')
    monkeypatch.setattr(config,'REPO_ROOT',tmp_path)
    root, directory, backend = config.DATA_ROOT, config.WORKSPACE_DIR, workspace.agent_backend
    code=asyncio.run(evaluate(parser().parse_args(['--smoke'])))
    assert code == 0
    assert (config.DATA_ROOT, config.WORKSPACE_DIR, workspace.agent_backend) == (root,directory,backend)
    files=list((tmp_path/'.dp-work/evals').glob('*/*.json'))
    reports=[json.loads(file.read_text()) for file in files]
    assert sum(report['total'] for report in reports)==10
    assert sum(report['passed_cases'] for report in reports)==10
    assert {report['suite'] for report in reports}=={'rag','agent','meetings'}
    assert len({report['experiment'] for report in reports})==3
    assert all(not report['uploaded'] and report['mode']=='smoke' for report in reports)
    assert all('must-not-leave-this-process' not in file.read_text() for file in files)


def test_gate_fails_for_unsafe_tools_fabrication_or_incomplete_execution():
    case=load_cases(case_id='agent-greeting-history')[0]
    value={'terminal':'done','answer':'你好','tools':[{'name':'execute'}]}
    scores=rules(case['inputs'],value,case['reference'])['results']
    assert next(row for row in scores if row['key']=='tool_boundary')['score']==0
    case=load_cases(case_id='rag-missing-fact')[0]
    scores=rules(case['inputs'],{'terminal':'done','answer':'无法确认，可能是180克','tools':[{'name':'search_knowledge'}]},case['reference'])['results']
    assert next(row for row in scores if row['key']=='no_forbidden_claim')['score']==0
    scores=rules({'suite':'agent'},{'terminal':'error','error':'TIMEOUT'},{'terminal':'done'})['results']
    assert scores[0]['score']==0
    case=load_cases(case_id='agent-sensitive-approval')[0]
    scores=rules(case['inputs'],{'terminal':'approval','files':{'.env.sample':'already written'}},case['reference'])['results']
    assert next(row for row in scores if row['key']=='no_premature_side_effect')['score']==0


def test_model_live_is_opt_in_and_cloud_requires_explicit_key(monkeypatch):
    assert parser().parse_args([]).mode=='smoke'
    assert not parser().parse_args(['--live']).upload
    with pytest.raises(ValueError,match='--judge'):
        asyncio.run(evaluate(parser().parse_args(['--smoke','--judge'])))
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    with pytest.raises(ValueError,match='LANGSMITH_API_KEY'):
        asyncio.run(evaluate(parser().parse_args(['--upload'])))
    with pytest.raises(ValueError,match='匹配'):
        load_cases(case_id='non-existent')


def test_remote_dataset_is_versioned_and_does_not_overwrite_existing_data():
    rows=load_cases(suite='rag')
    data=examples(rows,uuid4())
    class FakeClient:
        created=[]
        def read_dataset(self,**kwargs):return SimpleNamespace(id=data[0].dataset_id)
        def list_examples(self,**kwargs):return copy.deepcopy(data)
        def create_examples(self,**kwargs):self.created.append(kwargs)
    client=FakeClient()
    assert len(remote_examples(client,rows))==3
    assert client.created==[]
    data[0]=data[0].model_copy(update={'outputs':{'reference_answer':'远程内容已被用户改动'}})
    with pytest.raises(ValueError,match='未覆盖'):
        remote_examples(client,rows)
    assert client.created==[]


def test_target_runs_under_temporary_workspace_and_actual_file_checks():
    original=config.WORKSPACE_DIR
    case=load_cases(case_id='agent-write')[0]
    result=asyncio.run(Target('smoke',ModelSettings(api_key='fixture',base_url='https://eval.invalid',model='eval-smoke'))(case['inputs']))
    assert result['files']['draft.md']=='演示文档'
    assert result['terminal']=='done'
    assert config.WORKSPACE_DIR==original


def test_optional_judge_uses_reference_and_fails_closed_on_bad_score(monkeypatch):
    from evals import common as evaluators
    calls=[]
    async def good(messages,settings):
        calls.append(messages)
        return '{"score":1,"reason":"符合参考资料"}', 'fixture'
    monkeypatch.setattr(evaluators,'complete',good)
    judge=evaluators.model_judge(ModelSettings())
    result=asyncio.run(judge({'suite':'rag','question':'演示问题'},{'terminal':'done','answer':'演示回答'},{'reference_answer':'参考标准'}))
    assert result['score']==1 and '参考标准' in calls[0][1]['content']
    async def bad(*args):return '{"score":7}', 'fixture'
    monkeypatch.setattr(evaluators,'complete',bad)
    result=asyncio.run(judge({'suite':'rag'},{'terminal':'done','answer':'回答'},{}))
    assert result['score']==0 and '失败' in result['comment']


def test_new_remote_dataset_uses_server_example_versions():
    from datetime import datetime, timezone
    from langsmith.schemas import Example
    from langsmith.utils import LangSmithNotFoundError
    rows=load_cases(suite='minutes')
    class FakeClient:
        saved=[]
        def read_dataset(self,**kwargs):raise LangSmithNotFoundError('not found')
        def create_dataset(self,**kwargs):return SimpleNamespace(id=uuid4())
        def list_examples(self,**kwargs):return list(self.saved)
        def create_examples(self,**kwargs):
            self.saved=[Example(**row,dataset_id=kwargs['dataset_id'],created_at=datetime.now(timezone.utc)) for row in kwargs['examples']]
    client=FakeClient()
    data=remote_examples(client,rows)
    assert len(data)==2 and all(row.created_at.year>1970 for row in data)


def test_timed_out_target_does_not_leave_workspace_factory_patched():
    from src.agents import context
    original_sandbox = context.sandbox_backend
    root, directory, backend = config.DATA_ROOT, config.WORKSPACE_DIR, workspace.agent_backend
    target=Target('smoke',ModelSettings(),timeout=.01)
    async def slow(*args):await asyncio.Event().wait()
    target.run=slow
    output=asyncio.run(target({'suite':'agent'}))
    assert output['terminal']=='error' and output['error']=='TimeoutError'
    assert (config.DATA_ROOT, config.WORKSPACE_DIR, workspace.agent_backend)==(root,directory,backend)
    assert context.sandbox_backend is original_sandbox


def test_eval_reports_disabled_commands_and_restores_host_capability(monkeypatch):
    from src.agents import context
    monkeypatch.setattr(context, 'sandbox_backend', lambda: 'container')
    original_sandbox = context.sandbox_backend
    target = Target('smoke', ModelSettings())
    async def inspect(inputs, root):
        prompt = context.system_prompt('general')
        runtime = json.loads(prompt.split('<runtime_context>\n')[1].split('\n</runtime_context>')[0])
        assert runtime['execute_sandbox'] == 'unavailable'
        assert 'execute 不可用' in runtime['execute_limits']
        backend = workspace.agent_backend('general')
        result = await backend.aexecute('echo must-not-run')
        assert result.exit_code == 126
        assert '禁用' in result.output
        return {'terminal': 'done'}
    target.run = inspect
    assert asyncio.run(target({}))['terminal'] == 'done'
    assert context.sandbox_backend is original_sandbox
    assert context.sandbox_backend() == 'container'


def test_modules_have_separate_cases_and_scoring_rules():
    from evals.registry import MODULES
    assert set(MODULES)=={'rag','agent','meetings'}
    assert len(load_cases('agent'))==5 and len(load_cases('rag'))==3 and len(load_cases('meetings'))==2
    assert load_cases('minutes')==load_cases('meetings')
    scores=rules({'suite':'meetings'},{'terminal':'done','answer':'普通回答'},{'terminal':'done'})['results']
    assert next(row for row in scores if row['key']=='minutes_structure')['score']==0
    scores=rules({'suite':'rag'},{'terminal':'done','answer':'普通回答'},{'terminal':'done'})['results']
    assert not any(row['key']=='minutes_structure' for row in scores)
