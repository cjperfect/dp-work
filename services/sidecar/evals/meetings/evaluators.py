"""会议纪要：结构、关键事实及是否虚构已决结论。"""
import re
from src.meetings.minutes import SECTIONS
from ..common import base_checks

JUDGE_CRITERIA = '逐项对照原始转写：关键结论、行动项、负责人和时间准确且不遗漏；建议不写成已决定；保留分歧；没有明确的负责人或时间就标记未明确，不推断说话人身份。'


def rules(inputs, outputs, reference):
    result = base_checks(outputs, reference)
    answer = outputs.get('answer','')
    result.append({'key':'minutes_structure','score':int(all(f'## {section}' in answer.splitlines() for section in SECTIONS))})
    if reference.get('forbidden_regex'):
        result.append({'key':'no_forbidden_claim','score':int(re.search(reference['forbidden_regex'],answer,re.I) is None)})
    return {'results':result}
