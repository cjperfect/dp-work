"""在模型请求下一轮工具前阻止无进展的重复调用。"""
from collections import Counter
import hashlib
import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from ..providers.llm.schemas import ModelError


def fingerprint(value):
    """比较规范化后的参数和结果，不把正文保存在额外全局状态中。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).digest()


def call_key(call):
    return call['name'], fingerprint(call.get('args', {}))


def check_loop(messages, repeat_limit, error_limit):
    """最终回答始终允许；只拦截即将继续执行的工具。"""
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return
    # 同一批次内也不能并发执行大量完全相同的操作。
    if any(count > repeat_limit for count in Counter(call_key(call) for call in last.tool_calls).values()):
        raise ModelError('AGENT_REPEAT_LIMIT', 'Agent 请求了过多相同的并行工具操作，本批操作未执行，请调整任务后重试。')
    pending, completed = {}, []
    for message in messages[:-1]:
        if isinstance(message, HumanMessage):
            pending.clear()
            completed.clear()
        elif isinstance(message, AIMessage):
            pending.update((call['id'], call_key(call)) for call in message.tool_calls)
        elif isinstance(message, ToolMessage):
            key = pending.pop(message.tool_call_id, None)
            completed.append((key, fingerprint(message.content), message.status == 'error'))
    if len(completed) >= error_limit and all(item[2] for item in completed[-error_limit:]):
        raise ModelError('AGENT_TOOL_ERROR_LIMIT', f'工具已连续失败 {error_limit} 次，已停止继续执行，请检查错误或补充说明后重试。')
    recent = completed[-repeat_limit:]
    if len(recent) != repeat_limit or any(item != recent[0] for item in recent):
        return
    if recent[0][0] and any(call_key(call) == recent[0][0] for call in last.tool_calls):
        name = recent[0][0][0]
        raise ModelError('AGENT_REPEAT_LIMIT', f'工具「{name}」使用相同参数连续得到相同结果 {repeat_limit} 次，已阻止下一次重复执行。请调整任务或补充信息。')


class LoopGuardMiddleware(AgentMiddleware):
    """从图消息计算计数，天然隔离会话并兼容审批检查点恢复。"""
    def __init__(self, repeat_limit, error_limit):
        self.repeat_limit = repeat_limit
        self.error_limit = error_limit

    def after_model(self, state, runtime):
        check_loop(state['messages'], self.repeat_limit, self.error_limit)
        return None

    async def aafter_model(self, state, runtime):
        return self.after_model(state, runtime)
