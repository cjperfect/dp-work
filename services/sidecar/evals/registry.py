"""按业务板块选择案例、执行目标和评分器。"""
import json
from pathlib import Path
from .agent import targets as agent_targets, evaluators as agent_evaluators
from .rag import targets as rag_targets, evaluators as rag_evaluators
from .meetings import targets as meeting_targets, evaluators as meeting_evaluators
from .common import model_judge as common_judge

MODULES = {
    'rag': (rag_targets.Target, rag_evaluators),
    'agent': (agent_targets.Target, agent_evaluators),
    'meetings': (meeting_targets.Target, meeting_evaluators),
}


def canonical_suite(suite):
    return 'meetings' if suite == 'minutes' else suite


def load_cases(suite='all', case_id=None):
    """只读取各板块自己的合成案例文件。"""
    suite = canonical_suite(suite)
    if suite != 'all' and suite not in MODULES:
        raise ValueError('不支持的评测板块。')
    rows = []
    for name in MODULES:
        if suite != 'all' and name != suite:
            continue
        cases = json.loads((Path(__file__).parent / name / 'cases.json').read_text(encoding='utf-8'))
        if any(row['inputs']['suite'] != name for row in cases):
            raise ValueError('案例与所属评测板块不一致。')
        rows.extend(cases)
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('评测案例 ID 重复。')
    selected = [row for row in rows if (suite == 'all' or row['inputs']['suite'] == suite) and (not case_id or row['id'] == case_id)]
    if not selected:
        raise ValueError('没有匹配的评测案例。')
    return selected


class Target:
    def __init__(self, mode, settings, timeout=90):
        self.mode, self.settings, self.timeout = mode, settings, timeout

    async def __call__(self, inputs):
        target, _ = MODULES[canonical_suite(inputs['suite'])]
        return await target(self.mode, self.settings, self.timeout)(inputs)


def rules(inputs, outputs, reference_outputs):
    _, evaluator = MODULES[canonical_suite(inputs['suite'])]
    return evaluator.rules(inputs, outputs, reference_outputs or {})


def model_judge(settings):
    return common_judge(settings, lambda suite:MODULES[canonical_suite(suite)][1].JUDGE_CRITERIA)
