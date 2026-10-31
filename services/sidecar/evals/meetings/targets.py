"""会议纪要的结论、行动项、负责人、时间与忠实性评测。"""
import httpx
from src.meetings.minutes import generate
from src.meetings.schemas import MinutesInput
from ..common import IsolatedTarget

SMOKE_MINUTES = {
    'actions': '# 演示需求评审\n\n## 会议概述\n讨论上线范围。\n\n## 讨论要点\n先搜索，导出暂缓。\n\n## 明确结论\n先上线搜索功能。\n\n## 行动项\n小林在11月3日18点前提交搜索方案。\n\n## 待确认问题\n未明确。',
    'uncertain': '# 演示方案讨论\n\n## 会议概述\n讨论上线安排。\n\n## 讨论要点\n有人建议下个月上线，另一人反对，要求先补测试。\n\n## 明确结论\n未明确，上线时间尚未决定。\n\n## 行动项\n负责人：未明确；截止时间：未明确。\n\n## 待确认问题\n补测试及上线安排需继续讨论。',
}


class Target(IsolatedTarget):
    async def run(self, inputs, root):
        """复用生产纪要提示词与格式校验，不写入会议业务数据库。"""
        body = MinutesInput(task_id='eval-task',meeting_id='eval-meeting',source_revision=1,
            scheduled_at='2026-11-01T09:00:00+08:00',title=inputs['title'],segments=inputs['segments'])
        transport = None
        if self.mode == 'smoke':
            transport = httpx.MockTransport(lambda _: httpx.Response(200,json={
                'model':'eval-smoke','choices':[{'finish_reason':'stop','message':{'content':SMOKE_MINUTES[inputs['scenario']]}}]}))
        result = await generate(body, self.settings, transport)
        return {'terminal':'done','answer':result.content,'tools':[],'files':{}}
