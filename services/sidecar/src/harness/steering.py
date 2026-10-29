"""在模型调用边界消费引导，保留同一张图的工具结果和运行身份。"""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer


@dataclass
class RunInbox:
    owner: int | None
    thread_id: str
    pending: deque = field(default_factory=deque)
    seen: dict = field(default_factory=dict)


INBOXES: dict[str, RunInbox] = {}


@contextmanager
def active_run(run_id, owner, thread_id):
    inbox = RunInbox(owner, thread_id)
    if run_id in INBOXES:
        raise ValueError('运行已存在。')
    INBOXES[run_id] = inbox
    try:
        yield inbox
    finally:
        if INBOXES.get(run_id) is inbox:
            INBOXES.pop(run_id, None)


def deliver(run_id, owner, thread_id, key, content):
    """只向当前账号、原会话仍活跃的运行投递一次。"""
    inbox = INBOXES.get(run_id)
    if inbox is None or inbox.owner != owner or inbox.thread_id != thread_id:
        raise ValueError('当前运行已结束或不可接收引导。')
    if key in inbox.seen:
        if inbox.seen[key] != content:
            raise ValueError('引导内容不匹配。')
        return
    if len(inbox.seen) >= 50:
        raise ValueError('单次运行最多接收 50 条引导。')
    if sum(map(len, inbox.seen.values())) + len(content) > 120000:
        raise ValueError('单次运行的引导内容过长，请作为后续消息发送。')
    inbox.seen[key] = content
    inbox.pending.append({'id': key, 'content': content})


class SteeringMiddleware(AgentMiddleware):
    def __init__(self, run_id):
        self.run_id = run_id

    def consume(self):
        inbox = INBOXES.get(self.run_id)
        if inbox is None or not inbox.pending:
            return None
        messages = []
        while inbox.pending:
            item = inbox.pending.popleft()
            messages.append(HumanMessage(content=item['content'], id=item['id']))
            get_stream_writer()({'type': 'steering', **item})
        return {'messages': messages}

    async def abefore_model(self, state, runtime):
        return self.consume()

    @hook_config(can_jump_to=['model'])
    async def aafter_model(self, state, runtime):
        """最终回复前再检查一次，避免无工具调用时漏掉已收到的引导。"""
        last = state['messages'][-1]
        if isinstance(last, AIMessage) and not last.tool_calls:
            update = self.consume()
            if update:
                return {**update, 'jump_to': 'model'}
        return None
