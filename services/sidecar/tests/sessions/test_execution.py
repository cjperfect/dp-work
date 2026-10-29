"""工具展示记录的状态、幂等和大小限制。"""
from src.sessions.execution import record_tool, finish_tools


def test_tool_projection_is_idempotent_and_bounds_result():
    reply = {}
    event = {'type': 'tool_call', 'id': 'a', 'name': 'execute', 'args': {'command': 'pwd'}}
    record_tool(reply, event)
    record_tool(reply, event)
    assert len(reply['context']['tool_calls']) == 1
    result = record_tool(reply, {'type': 'tool_result', 'id': 'a', 'content': 'x' * 40000, 'status': 'error'})
    assert result['trace']['status'] == 'failed'
    assert result['trace']['truncated']
    assert len(result['trace']['result']) == 32000
    finish_tools(reply)
    assert result['trace']['status'] == 'failed'


def test_unfinished_tools_are_closed_on_stop():
    reply = {}
    record_tool(reply, {'type': 'tool_call', 'id': 'b', 'name': 'read_file', 'args': {}})
    finish_tools(reply)
    call = reply['context']['tool_calls'][0]
    assert call['status'] == 'cancelled'
    assert call['ended_at'] >= call['started_at']
