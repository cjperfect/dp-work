"""RAG：引用、资料不足时的拒答与禁止编造。"""
import re
from ..common import base_checks, tool_checks

JUDGE_CRITERIA = '回答必须基于检索到的文档；事实与引用对应；资料没有答案或索引未就绪时明确说明，不编造事实，也不能误说文档不存在。固定检索夹具不代表真实召回率。'


def rules(inputs, outputs, reference):
    result = base_checks(outputs, reference) + tool_checks(outputs, reference)
    answer = outputs.get('answer','')
    if reference.get('citation'):
        result.append({'key':'citation','score':int(reference['citation'] in answer)})
    if reference.get('abstain'):
        result.append({'key':'abstention','score':int(bool(re.search(r'未提供|未给出|无法确认|没有.{0,12}(重量|信息)|未.{0,6}重量|不知道|无法确定', answer)))})
    if reference.get('forbidden_regex'):
        result.append({'key':'no_forbidden_claim','score':int(re.search(reference['forbidden_regex'],answer,re.I) is None)})
    return {'results':result}
