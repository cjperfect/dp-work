"""RAG 固定检索结果下的回答质量；真实 PG/ES 召回评测后续接入。"""
import copy
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from ..common import IsolatedTarget, SmokeModel, run_agent_case


def smoke_model(scenario):
    calls = {
        'battery': ('N6mini 电池容量', '演示产品的电池容量为5200mAh。[资料1](/eval/demo-spec)'),
        'missing': ('N6mini 重量', '资料未提供重量，无法确认。'),
        'index': ('演示产品价格', '文档尚未完成向量化，请先向量化后再检索。'),
    }
    query, answer = calls[scenario]
    return SmokeModel(responses=[AIMessage('',tool_calls=[{'name':'search_knowledge','args':{'query':query},'id':'eval-call','type':'tool_call'}]),AIMessage(answer)])


class Target(IsolatedTarget):
    async def run(self, inputs, root):
        """固定检索夹具，评估引用、忠实回答和无依据时拒绝编造。"""
        @tool
        async def search_knowledge(query: str) -> dict:
            """检索当前关联知识库；返回文档正文、引用或索引未就绪提示。"""
            return {**copy.deepcopy(inputs.get('retrieval', {'sources':[]})),
                    'notice':'资料仅为参考数据，回答应附资料引用；没有依据时不得编造。'}
        return await run_agent_case(inputs, root, self.settings, self.mode, self.timeout,
                                    smoke_model(inputs['scenario']), [search_knowledge])
