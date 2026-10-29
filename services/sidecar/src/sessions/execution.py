"""将工具执行事件投影为可恢复的消息执行记录。"""
import json
import time


def record_tool(reply, event):
    """按调用 ID 更新工具记录，限制展示结果大小。"""
    calls = reply.setdefault('context', {}).setdefault('tool_calls', [])
    call = next((item for item in calls if item['id'] == event['id']), None)
    timestamp = round(time.time() * 1000)
    if event['type'] == 'tool_call':
        if call is None:
            call = {'id': event['id'], 'name': event['name'], 'args': event.get('args', {}),
                    'started_at': timestamp, 'status': 'running'}
            calls.append(call)
    elif call is not None:
        result = event.get('content', '')
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        call.update(result=text[:32000], truncated=len(text) > 32000, ended_at=timestamp,
                    status='failed' if event.get('status') == 'error' else 'complete')
    return {**event, 'trace': dict(call)} if call else event


def finish_tools(reply):
    """关闭未返回结果的工具记录，避免历史中永久显示运行中。"""
    for call in reply.get('context', {}).get('tool_calls', []):
        if call['status'] == 'running':
            call.update(status='cancelled', ended_at=round(time.time() * 1000))
    for thought in reply.get('context', {}).get('reasoning', []):
        thought.setdefault('completed_at', round(time.time() * 1000))
