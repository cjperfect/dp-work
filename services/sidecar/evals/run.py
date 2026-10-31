"""LangSmith 离线评测入口：默认不调用模型、不上传任何数据。"""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from langsmith import Client, aevaluate, tracing_context
from langsmith.schemas import Example
from langsmith.utils import LangSmithNotFoundError

from src import config
from src.agents.agent import settings_for
from src.meetings.minutes import PROMPT_FILE, PROMPT_VERSION
from src.providers.llm.schemas import ModelSettings
from .registry import MODULES, Target, load_cases, model_judge, rules



def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]


def examples(rows, dataset_id=None):
    name = 'dp-work-eval-' + fingerprint(rows)
    return [Example(id=uuid5(NAMESPACE_URL,name + '/' + row['id']),
        dataset_id=dataset_id or uuid5(NAMESPACE_URL,name), inputs=row['inputs'],outputs=row['reference'],
        metadata={'case_id':row['id'],'synthetic':True}) for row in rows]


def remote_examples(client, rows):
    """按内容版本建立独立数据集；已有数据不一致时拒绝覆盖。"""
    name = 'dp-work-' + rows[0]['inputs']['suite'] + '-synthetic-' + fingerprint(rows)
    try:
        dataset = client.read_dataset(dataset_name=name)
    except LangSmithNotFoundError:
        dataset = client.create_dataset(dataset_name=name, description='DP Work 合成评测案例；不含真实用户会话。')
    desired = examples(rows, dataset.id)
    existing = list(client.list_examples(dataset_id=dataset.id))
    if not existing:
        client.create_examples(dataset_id=dataset.id, examples=[{
            'id':row.id,'inputs':row.inputs,'outputs':row.outputs,'metadata':row.metadata} for row in desired])
        existing = list(client.list_examples(dataset_id=dataset.id))
    actual = {row.id:(row.inputs,row.outputs) for row in existing}
    expected = {row.id:(row.inputs,row.outputs) for row in desired}
    if actual != expected:
        raise ValueError('LangSmith 数据集内容与本地版本不一致，已停止，未覆盖远程内容。')
    by_id = {row.id:row for row in existing}
    # 使用服务端版本时间，避免实验被错误关联到 1970 年的本地 Example 默认版本。
    return [by_id[row.id] for row in desired]


def metadata(args, rows):
    try:
        revision = subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError):
        revision = 'unknown'
    from templates import read_template
    return {'agent_prompt_sha':hashlib.sha256(read_template('general').encode()).hexdigest(),
            'eval_code_sha':hashlib.sha256(b''.join(str(path.relative_to(Path(__file__).parent)).encode() + path.read_bytes() for path in sorted(Path(__file__).parent.rglob('*.py')))).hexdigest(),
            'agent_code_sha':hashlib.sha256((config.SERVICE_ROOT/'src/agents/agent.py').read_bytes() + (config.SERVICE_ROOT/'src/agents/context.py').read_bytes()).hexdigest(),
            'mode':args.mode,'synthetic':True,'suite':args.suite,'cases_version':fingerprint(rows),
            'git_revision':revision, 'minutes_prompt_version':PROMPT_VERSION,
            'minutes_prompt_sha':hashlib.sha256(PROMPT_FILE.read_bytes()).hexdigest(),
            'evaluation_focus':{'rag':'fixed-retrieval-grounded-generation','agent':'tool-selection-task-completion-approval','meetings':'conclusions-actions-owner-deadline-faithfulness'}[args.suite], 'judge':args.judge}


async def evaluate_suite(args, rows, settings, client):
    """每个业务板块单独创建实验和报告，便于独立对比与回归。"""
    experiment_metadata = {**metadata(args,rows), 'model':settings.model, 'max_tokens':args.max_tokens}
    data = await asyncio.to_thread(remote_examples,client,rows) if args.upload else examples(rows)
    scorers = [rules, *([model_judge(settings)] if args.judge else [])]
    with tracing_context(enabled=args.upload,client=client):
        target = Target(args.mode,settings,args.timeout)
        results = await aevaluate(target.__call__,data=data,evaluators=scorers,
            client=client,upload_results=args.upload,max_concurrency=1,num_repetitions=args.repetitions,
            experiment_prefix=f'dp-work-{args.mode}-{args.suite}',metadata=experiment_metadata)
        records = []
        async for row in results:
            run = row['run']
            scores = [{'key':value.key,'score':value.score,'comment':value.comment} for value in row['evaluation_results']['results']]
            records.append({'case_id':(row['example'].metadata or {}).get('case_id'), 'suite':args.suite,
                'outputs':run.outputs,'error':bool(run.error),'scores':scores,
                'passed':not run.error and bool(scores) and all(value['score'] == 1 for value in scores)})
    expected_count = len(rows) * args.repetitions
    passed = len(records) == expected_count and all(row['passed'] for row in records)
    report = {'experiment':results.experiment_name,'mode':args.mode,'uploaded':args.upload,'suite':args.suite,
        'model':settings.model, 'metadata':experiment_metadata,'expected_cases':expected_count,
        'total':len(records),'passed':passed,'passed_cases':sum(row['passed'] for row in records),'results':records}
    output = config.REPO_ROOT / '.dp-work/evals' / args.suite
    output.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',prefix=stamp+'-',suffix='.json',dir=output,delete=False) as file:
        json.dump(report,file,ensure_ascii=False,indent=2,default=str)
    print(f"板块：{args.suite}；模式：{args.mode}；通过 {report['passed_cases']}/{report['total']}；上传：{'是' if args.upload else '否'}")
    print('报告：' + file.name)
    if args.upload: print('LangSmith 实验：' + results.experiment_name)
    return report


async def evaluate(args):
    """运行指定板块；全部运行时也保持数据集、实验及报告分开。"""
    if args.judge and args.mode != 'live':
        raise ValueError('--judge 仅用于 --live，避免冒烟检查产生真实模型调用。')
    if args.upload and not os.environ.get('LANGSMITH_API_KEY','').strip():
        raise ValueError('请先在 services/sidecar/.env 填写 LANGSMITH_API_KEY，再使用 --upload。')
    rows = load_cases(args.suite, args.case)
    settings = settings_for() if args.mode == 'live' else ModelSettings(api_key='eval-fixture',model='eval-smoke',base_url='https://eval.invalid/v1')
    from dataclasses import replace
    settings = replace(settings,max_tokens=args.max_tokens,timeout=args.timeout)
    # 客户端零采样阻止 SDK 内部目标追踪覆盖本地 tracing_context 后产生上传。
    client = Client(tracing_sampling_rate=1) if args.upload else Client(
        api_url='http://127.0.0.1:1',api_key='local-only',auto_batch_tracing=False,tracing_sampling_rate=0)
    try:
        reports = []
        for suite in MODULES:
            selected = [row for row in rows if row['inputs']['suite'] == suite]
            if selected:
                batch = argparse.Namespace(**{**vars(args), 'suite':suite})
                reports.append(await evaluate_suite(batch,selected,settings,client))
        print(f"汇总：通过 {sum(row['passed_cases'] for row in reports)}/{sum(row['total'] for row in reports)}，共 {len(reports)} 个板块")
        if args.mode == 'smoke': print('冒烟结果仅验证评测链路，不代表真实模型质量。')
        return 0 if all(row['passed'] for row in reports) else 1
    finally:
        await asyncio.to_thread(client.close)


def bounded(minimum, maximum):
    def parse(value):
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f'请输入 {minimum}–{maximum} 之间的整数。')
        return number
    return parse


def parser():
    result = argparse.ArgumentParser(description='DP Work 合成数据离线评测；默认 smoke，不调用真实模型或上传数据。')
    mode = result.add_mutually_exclusive_group()
    mode.add_argument('--live',dest='mode',action='store_const',const='live',help='调用 .env 中的模型，消耗模型额度')
    mode.add_argument('--smoke',dest='mode',action='store_const',const='smoke',help='使用固定模型替身检查链路')
    result.set_defaults(mode='smoke')
    result.add_argument('--suite',choices=['all','rag','agent','meetings','minutes'],default='all')
    result.add_argument('--case',help='只运行一个案例 ID')
    result.add_argument('--upload',action='store_true',help='明确上传合成案例、输出及执行 trace 到 LangSmith')
    result.add_argument('--judge',action='store_true',help='额外调用模型进行语义评分，消耗模型额度')
    result.add_argument('--repetitions',type=int,choices=range(1,6),default=1)
    result.add_argument('--timeout',type=bounded(10,600),default=90)
    result.add_argument('--max-tokens',type=bounded(256,8192),default=2048)
    return result


def main():
    args = parser().parse_args()
    try:
        code = asyncio.run(evaluate(args))
    except (ValueError,OSError) as cause:
        print('评测启动失败：' + str(cause))
        code = 2
    except Exception as cause:
        print('评测服务连接或执行失败：' + type(cause).__name__ + '，请检查本地配置。')
        code = 2
    raise SystemExit(code)


if __name__ == '__main__':
    main()
