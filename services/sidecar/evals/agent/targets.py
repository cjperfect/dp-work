"""Agent / Harness 的工具选择与实际任务执行。"""
from langchain_core.messages import AIMessage
from ..common import IsolatedTarget, SmokeModel, run_agent_case


def smoke_model(scenario):
    """固定模型替身仅校验评测链路，不能用于衡量真实模型质量。"""
    calls = {
        'write': ('write_file', {'file_path':'draft.md','content':'演示文档'}, '已创建演示文档。'),
        'approval': ('write_file', {'file_path':'.env.sample','content':'DEMO=1'}, ''),
        'read': ('read_file', {'file_path':'notes.txt'}, '演示团队的值班开始时间是09:30。'),
    }
    if scenario in calls:
        name, args, answer = calls[scenario]
        return SmokeModel(responses=[AIMessage('',tool_calls=[{'name':name,'args':args,'id':'eval-call','type':'tool_call'}]),AIMessage(answer or '等待审批。')])
    return SmokeModel(responses=[AIMessage('你好，有什么可以帮你？' if scenario == 'greeting' else '不客气！')])


class Target(IsolatedTarget):
    async def run(self, inputs, root):
        """使用真实执行图评测；模型替身仅用于冒烟。"""
        return await run_agent_case(inputs, root, self.settings, self.mode, self.timeout, smoke_model(inputs['scenario']))
