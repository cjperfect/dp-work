"""将当前分支的执行证据带入新一轮，不恢复已取消的进程或检查点。"""
import json

MAX_CONTEXT = 18000
MAX_MESSAGES = 8


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def execution_context(state, path, history):
    """只使用当前分支及当前项目的历史；限制工具结果和整体输入大小。"""
    budget = min(MAX_CONTEXT, max(0, 120000 - sum(len(row['content']) for row in history)))
    if budget < 500:
        return ''
    active = set(path)
    nodes = state['nodes']
    runs = state.get('runs', {})
    project_id = state['thread'].get('project_id')
    records = []
    candidates = [(index, nodes[mid]) for index, mid in enumerate(path)
                  if mid in nodes and nodes[mid]['role'] == 'assistant'][-MAX_MESSAGES:]
    for index, node in reversed(candidates):
        context = node.get('context', {})
        usage = context.get('usage') if isinstance(context.get('usage'), dict) else {}
        run_id = context.get('execution_run_id') or usage.get('run_id')
        run_id = run_id if isinstance(run_id, str) else None
        run = runs.get(run_id) or next((row for row in runs.values() if row.get('response_id') == node['id']), None)
        # 旧记录缺少项目身份时，不能猜测它属于当前选择的项目。
        if run and run.get('project_id') != project_id:
            continue
        if not run and project_id is not None:
            continue
        tools = context.get('tool_calls', [])
        tools = [tool for tool in tools if isinstance(tool, dict) and isinstance(tool.get('name'), str)] if isinstance(tools, list) else []
        changes = context.get('file_changes', [])
        changes = [change for change in changes if isinstance(change, dict)] if isinstance(changes, list) else []
        interrupted = node.get('status') in ('cancelled', 'failed') or (run and run['status'] in ('cancelled', 'failed', 'interrupted'))
        if not tools and not changes and not interrupted:
            continue
        previous_users = [nodes[mid] for mid in path[:index] if nodes[mid]['role'] == 'user']
        latest = previous_users[-1]['content'] if previous_users else ''
        request_id = (run or {}).get('request_message_id')
        request = nodes[request_id]['content'] if request_id in active else latest
        record = {'message_id': node['id'], 'run_id': (run or {}).get('id'),
                  'status': (run or {}).get('status', node.get('status')),
                  'request': request[:1600], 'request_truncated': len(request) > 1600,
                  'latest_instruction': latest[:1000],
                  'partial_reply': node.get('content', '')[-1200:] if interrupted else '',
                  'tool_count': len(tools), 'file_change_count': len(changes),
                  'tools_omitted': max(0, len(tools) - 12), 'files_omitted': max(0, len(changes) - 12),
                  'tools': [{'name': tool['name'], 'status': 'returned' if tool.get('status') == 'complete' else tool.get('status', 'unknown'),
                             'args_preview': encoded(tool.get('args', {}))[:900],
                             'result_preview': str(tool.get('result', ''))[:1500],
                             'result_truncated': bool(tool.get('truncated')) or len(str(tool.get('result', ''))) > 1500}
                            for tool in tools[-12:]],
                  'files': [{'path': str(change.get('path', ''))[:500], 'kind': change.get('kind'),
                             'undone': bool(change.get('undone')), 'preview_unavailable': bool(change.get('unavailable'))}
                            for change in changes[-12:]]}
        while record['tools'] and len(encoded([record, *records])) > budget:
            record['tools'].pop(0)
            record['tools_omitted'] = record['tool_count'] - len(record['tools'])
        while record['files'] and len(encoded([record, *records])) > budget:
            record['files'].pop(0)
            record['files_omitted'] = record['file_change_count'] - len(record['files'])
        record['tools_omitted'] = record['tool_count'] - len(record['tools'])
        record['files_omitted'] = record['file_change_count'] - len(record['files'])
        if len(encoded([record, *records])) <= budget:
            records.insert(0, record)
    return encoded(records) if records else ''
