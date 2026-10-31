"""本地会话 CRUD、分支、执行与审批；不将会话正文写入云端业务表。"""
import asyncio
import copy
import re
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .storage import storage, SessionError, now
from .schemas import ThreadCreate, DraftSave, GraphSave, RenameThread, ImportThread
from .execution import record_tool, finish_tools

ACTIVE = {}


async def io(function, *args):
    """文件和 SQLite 操作在线程中执行，取消时等待已开始的落盘完成。"""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def require(state):
    if not state or state.get('deleted'):
        raise SessionError('会话不存在。', 404)


def current(state):
    return state.get('runs', {}).get(state.get('run_id'))


def unlocked(state, revision=None):
    require(state)
    run = current(state)
    if run and run['status'] == 'running':
        raise SessionError('该会话正在运行或等待审批，请先停止。')
    if revision is not None and revision != state['thread']['draft_revision']:
        raise SessionError('会话已在其他页面更新，请重新加载。')


def touch(state):
    state['thread']['draft_revision'] += 1
    state['thread']['updated_at'] = now()


def detail(state):
    require(state)
    nodes = state['nodes']
    def message(row, seq=0):
        result = {**{k: v for k, v in row.items() if k != 'parentId'}, 'seq': seq,
                  'context': {k:v for k,v in row.get('context', {}).items() if k != 'recovery'}}
        run = state.get('runs', {}).get(row.get('context', {}).get('execution_run_id'))
        if run and run.get('recoverable') and row['id'] == (state.get('active_path') or [None])[-1] and not current(state):
            from ..harness.recovery import has_checkpoint
            if has_checkpoint(run['id']):
                result['context'] = {**row.get('context', {}), 'recovery':{'run_id':run['id']}}
        return result
    history = any(m['role'] == 'user' for m in nodes.values()) and any(
        m['role'] == 'assistant' and m['status'] == 'complete' and m['content'].strip() for m in nodes.values())
    return {'thread': {**state['thread'], 'has_history': bool(history)},
            'knowledge_base_ids': state['knowledge_base_ids'],
            'messages': [message(nodes[mid], i + 1) for i, mid in enumerate(state['active_path']) if mid in nodes],
            'message_branches': [{'parentId': row.get('parentId'), 'message': message(row)} for row in nodes.values()]}


def new_state(body):
    timestamp = now()
    return {'thread': {'id': body['id'], 'agent_id': body['agent_id'], 'project_id': body.get('project_id'),
                      'title': '新会话', 'title_source': 'pending', 'draft': '', 'draft_revision': 0,
                      'created_at': timestamp, 'updated_at': timestamp, 'has_history': False},
            'knowledge_base_ids': body.get('knowledge_base_ids', []), 'active_path': [],
            'nodes': {}, 'runs': {}, 'approvals': {}, 'steering': {}, 'run_id': None, 'deleted': False}


def graph(state, body, importing=False):
    body = GraphSave.model_validate({k: body[k] for k in ('expected_revision', 'messages', 'message_branches') if k in body}).model_dump(mode='json')
    entries = {entry['message']['id']: {**entry['message'], 'parentId': entry['parentId']} for entry in body['message_branches']}
    for i, message in enumerate(body['messages']):
        entries[message['id']] = {**message, 'parentId': body['messages'][i - 1]['id'] if i else None}
    merged = {**state['nodes'], **entries}
    if len(merged) > 5000 or sum(len(m['content']) + len(str(m['context'])) for m in merged.values()) > 4000000:
        raise SessionError('会话过大，请新建会话。', 400)
    for mid, row in entries.items():
        previous = state['nodes'].get(mid)
        row.get('context', {}).pop('recovery', None)
        if previous and (previous.get('parentId') != row['parentId'] or previous['role'] != row['role']):
            raise SessionError('消息节点归属不可更改。')
        if importing and row['status'] in ('streaming', 'waiting_approval'):
            row['status'] = 'cancelled'
        if (previous or {}).get('context', {}).get('usage'):
            row.setdefault('context', {})['usage'] = copy.deepcopy(previous['context']['usage'])
        if (previous or {}).get('context', {}).get('execution_run_id'):
            row.setdefault('context', {})['execution_run_id'] = previous['context']['execution_run_id']
        if 'memory_sources' in (previous or {}).get('context', {}):
            row.setdefault('context', {})['memory_sources'] = copy.deepcopy(previous['context']['memory_sources'])
        undone = {change['id'] for change in (previous or {}).get('context', {}).get('file_changes', []) if change.get('undone')}
        for change in row.get('context', {}).get('file_changes', []):
            if change.get('id') in undone:
                change['undone'] = True
    state['nodes'].update(entries)
    state['active_path'] = [row['id'] for row in body['messages']]
    touch(state)


def finish(state, status, code=None, error=None):
    run = current(state)
    if not run or run['status'] != 'running':
        return
    run.update(status=status, error_code=code, error_message=error, finished_at=now(), recoverable=status != 'completed')
    reply = state['nodes'].get(run['response_id'])
    if reply:
        finish_tools(reply)
    if reply and reply['status'] in ('streaming', 'waiting_approval'):
        reply['status'] = 'complete' if status == 'completed' else 'cancelled' if status == 'cancelled' else 'failed'
    for approval in state['approvals'].values():
        if approval['run_id'] == run['id']:
            approval['actionable'] = False
    state['run_id'] = None
    state['steering'] = {}
    touch(state)


async def recover(owner, key):
    """进程重启后保留待审批 checkpoint，其他未完成执行标记为中断。"""
    def operation(state):
        require(state)
        for row in state.get('runs', {}).values():
            if row['status'] in ('cancelled', 'interrupted', 'failed'):
                reconcile_files(owner, state, row)
            if row['status'] in ('cancelled', 'interrupted', 'failed', 'completed'):
                reconcile_usage(state, row)
        run = current(state)
        if not run or run['status'] != 'running':
            return
        reply = state['nodes'].get(run['response_id'], {})
        expired = datetime.fromisoformat(run['deadline_at']) <= datetime.now(timezone.utc)
        if expired or ((owner, run['id']) not in ACTIVE and reply.get('status') != 'waiting_approval'):
            finish(state, 'interrupted', 'RUN_INTERRUPTED', '执行中断，请重试。')
            reconcile_files(owner, state, run)
            reconcile_usage(state, run)
    await io(storage.mutate, owner, key, 'run_recovered', operation)


def reconcile_files(owner, state, run):
    """中断后的会话从本机执行索引补齐 Diff，避免丢失撤销入口。"""
    from ..tools.file_snapshots import run_changes
    reply = state['nodes'].get(run.get('response_id'))
    if not reply:
        return
    known = {change['id'] for node in state['nodes'].values() for change in node.get('context', {}).get('file_changes', [])}
    for change in run_changes(owner, run['id']):
        if change['id'] not in known:
            reply.setdefault('context', {}).setdefault('file_changes', []).append(change)
            known.add(change['id'])
            touch(state)


def reconcile_usage(state, run):
    """流中断后仍保留已报告用量；未知消耗不能视为零。"""
    from ..harness.usage import read_usage
    if not isinstance(run.get('id'), str) or not re.fullmatch(r'[a-fA-F0-9-]{36}', run['id']):
        return
    usage = read_usage(run['id'])
    if not usage:
        return
    if run['status'] != 'running':
        for call in usage['calls']:
            if call['status'] == 'running':
                call['status'] = 'unreported'
        usage['unreported_calls'] = sum(call['status'] == 'unreported' for call in usage['calls'])
        usage['in_flight_calls'] = 0
        usage['complete'] = bool(usage['calls']) and not usage['unreported_calls']
    run['usage'] = usage
    reply = state['nodes'].get(run.get('response_id'))
    if reply:
        reply.setdefault('context', {})['usage'] = copy.deepcopy(usage)


async def operation(action, params, rpc_state=None):
    """分发有界的本地会话操作，owner_id 由已认证 API 注入。"""
    owner, key, body = params['owner_id'], params.get('thread_id'), params.get('body', {})
    if action == 'resume.lookup':
        await recover(owner, key)
        state = await io(storage.get, owner, key)
        require(state)
        row = state['runs'].get(body.get('run_id'))
        if not row or row['response_id'] != state['active_path'][-1] or not row.get('recoverable'):
            raise SessionError('原任务不可恢复，请重新加载会话。')
        return {'thread': state['thread'], 'knowledge_base_ids': row.get('knowledge_base_ids', [])}
    if action == 'files.undo':
        from ..tools.file_snapshots import undo, SnapshotError
        from ..tools.workspace import agent_workspace
        from ..tools.projects import project_workspace
        def restore(state):
            unlocked(state)
            change_id = body.get('change_id')
            records = [change for node in state['nodes'].values()
                       for change in node.get('context', {}).get('file_changes', []) if change.get('id') == change_id]
            if not records:
                raise SessionError('当前会话中没有这次文件修改。', 404)
            code = {1: 'general', 2: 'product', 3: 'ui'}[state['thread']['agent_id']]
            root = project_workspace(state['thread']['project_id'], owner) if state['thread'].get('project_id') else agent_workspace(code)
            try:
                result = undo(owner, change_id, root)
            except (SnapshotError, OSError, ValueError) as cause:
                raise SessionError(str(cause)) from cause
            for record in records:
                record.update(result)
            touch(state)
            return {'change': result, 'thread': copy.deepcopy(state['thread'])}
        return await io(storage.mutate, owner, key, 'file_change_undone', restore)
    if action in ('images.save', 'images.read'):
        from . import images
        return await io(images.save, owner, body) if action == 'images.save' else await io(images.read, owner, body.get('id', ''), body.get('content_type'))
    if action == 'project.detach':
        def detach():
            import json
            with storage.lock:
                db = storage._open(owner)
                try:
                    states = [json.loads(row[0]) for row in db.execute('SELECT state_json FROM threads WHERE deleted=0')]
                finally:
                    db.commit()
                    db.close()
                targets = [s for s in states if s['thread']['project_id'] == body['project_id']]
                for state in targets:
                    unlocked(state)
                for state in targets:
                    def clear(s):
                        unlocked(s)
                        s['thread']['project_id'] = None
                        touch(s)
                    storage.mutate(owner, state['thread']['id'], 'project_detached', clear)
        return await io(detach)
    if action == 'approval.lookup':
        def lookup():
            import json
            with storage.lock:
                db = storage._open(owner)
                try:
                    for row in db.execute('SELECT state_json FROM threads WHERE deleted=0'):
                        state = json.loads(row[0])
                        if body['approval_id'] in state['approvals']:
                            return detail(state)
                finally:
                    db.commit()
                    db.close()
            raise SessionError('审批不存在。', 404)
        return await io(lookup)
    if action == 'list':
        rows = await io(storage.list, owner)
        return [row for row in rows if (not body.get('agent_id') or row['agent_id'] == body['agent_id'])
                and body.get('q', '').strip().casefold() in row['title'].casefold()]
    if action == 'create':
        body = ThreadCreate.model_validate(body).model_dump(mode='json')
        key = body['id']
        def create(state):
            if body.get('project_id'):
                from .projects import get
                get(owner, body['project_id'])
            if not state:
                state.update(new_state(body))
            require(state)
            if state['thread']['agent_id'] != body['agent_id'] or state['thread']['project_id'] != body.get('project_id'):
                raise SessionError('会话与 Agent 或项目不匹配。')
            return detail(state)
        return await io(storage.mutate, owner, key, 'session_created', create)
    if action == 'import':
        imported = ImportThread.model_validate(body).model_dump(mode='json')
        key = imported['thread']['id']
        def migrate(state):
            if state.get('deleted'):
                return None
            if not state:
                state.update(new_state({**imported['thread'], 'knowledge_base_ids': imported['knowledge_base_ids']}))
                state['thread'].update(imported['thread'])
                state['thread']['project_id'] = body.get('project_id')
                graph(state, imported, True)
                state['thread']['updated_at'] = imported['thread']['updated_at']
            return detail(state)
        return await io(storage.mutate, owner, key, 'session_imported', migrate)
    if action in ('get', 'draft', 'messages', 'rename', 'delete', 'project'):
        if action != 'rename':
            await recover(owner, key)
        def update(state):
            require(state)
            if action == 'draft':
                data = DraftSave.model_validate(body).model_dump(mode='json')
                unlocked(state, data['expected_revision'])
                state['thread']['draft'], state['knowledge_base_ids'] = data['draft'], data['knowledge_base_ids']
                touch(state)
                return detail(state)['thread']
            if action == 'messages':
                unlocked(state, body['expected_revision'])
                graph(state, body)
            elif action == 'rename':
                data = RenameThread.model_validate(body).model_dump()
                if data['title_source'] == 'manual' or (state['thread']['title_source'] == 'pending' and state['active_path'] and state['active_path'][0] == data['first_message_id']):
                    if not data['title'].strip():
                        raise SessionError('请输入会话标题。', 400)
                    state['thread'].update(title=data['title'].strip(), title_source=data['title_source'], updated_at=now())
                return detail(state)['thread']
            elif action == 'delete':
                finish(state, 'cancelled', 'CONVERSATION_DELETED', '会话已删除。')
                state.update(deleted=True, nodes={}, active_path=[], approvals={}, runs={}, steering={}, knowledge_base_ids=[])
                state['thread'].update(title='已删除', draft='')
                return None
            elif action == 'project':
                if body.get('project_id'):
                    from .projects import get
                    get(owner, body['project_id'])
                unlocked(state, body['expected_revision'])
                state['thread']['project_id'] = body.get('project_id')
                touch(state)
            return detail(state)
        if action == 'delete':
            initial = await io(storage.get, owner, key)
            checkpoints = list(initial.get('runs', {}))
            run = current(initial)
            task = ACTIVE.get((owner, run['id'])) if run else None
            if task and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        result = await io(storage.mutate, owner, key, 'session_' + action, update)
        if action == 'delete':
            await io(storage.purge_deleted, owner, key)
            for checkpoint_id in checkpoints:
                await cleanup_checkpoint(checkpoint_id)
        return result
    if action == 'steer':
        return await steer(owner, key, body)
    if action.startswith('runs.'):
        return await runs(action[5:], owner, body)
    if action == 'approvals':
        await recover(owner, key)
        state = await io(storage.get, owner, key)
        return list(state['approvals'].values())[-20:]
    raise SessionError('不支持的会话操作。', 400)


async def runs(action, owner, body):
    # 尚未进入历史列表的首轮运行仍需支持查询和停止。
    if body.get('conversation_id'):
        key = body['conversation_id']
        await recover(owner, key)
        states = [await io(storage.get, owner, key)]
    else:
        def all_states():
            with storage.lock:
                db = storage._open(owner)
                try:
                    import json
                    return [json.loads(row[0]) for row in db.execute('SELECT state_json FROM threads WHERE deleted=0')]
                finally:
                    db.commit()
                    db.close()
        states = await io(all_states)
        for state in states:
            await recover(owner, state['thread']['id'])
        states = await io(all_states)
    rows = [r for s in states for r in s['runs'].values() if not body.get('status') or r['status'] == body['status']]
    if action == 'list':
        rows.sort(key=lambda r: (r['started_at'], r['id']), reverse=True)
        page, size = max(1, int(body.get('page', 1))), min(100, max(1, int(body.get('page_size', 20))))
        return {'item': rows[(page - 1) * size:page * size], 'page': page, 'page_size': size, 'total': len(rows)}
    row = next((r for r in rows if r['id'] == body['run_id']), None)
    if not row:
        raise SessionError('运行不存在。', 404)
    if action == 'cancel' and row['status'] in ('running', 'cancelled'):
        task = ACTIVE.get((owner, row['id']))
        def cancel(state):
            if state.get('run_id') == row['id']:
                finish(state, 'cancelled', 'USER_CANCELLED', '用户已停止运行。')
            return state['runs'][row['id']]
        row = await io(storage.mutate, owner, row['conversation_id'], 'run_cancelled', cancel)
        if task and task is not asyncio.current_task():
            if not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        saved = await io(storage.get, owner, row['conversation_id'])
        row = saved['runs'][row['id']]
    return row


async def cleanup_checkpoint(run_id):
    from ..harness.approvals import remove_checkpoint
    from .. import config
    await io(remove_checkpoint, config.WORKSPACE_DIR.parent / 'data' / 'agent-checkpoints' / (run_id + '.sqlite3'))


async def steer(owner, key, body):
    from ..harness.steering import deliver
    content, mid = body['content'], body['id']
    if not content.strip() or len(content) > 120000:
        raise SessionError('请输入有效的引导内容。', 400)
    def enqueue(state):
        require(state)
        applied = state['nodes'].get(mid)
        if applied and applied.get('context', {}).get('steering_status') == 'applied':
            if applied['content'] != content:
                raise SessionError('引导消息内容不匹配。')
            return {'id': mid, 'status': 'applied'}
        previous = state['steering'].get(mid)
        if previous:
            if previous['content'] != content:
                raise SessionError('引导消息内容不匹配。')
            if previous['status'] == 'applied':
                return {'id': mid, 'status': 'applied'}
        run = current(state)
        if not run or run['status'] != 'running' or state['nodes'][run['response_id']]['status'] == 'waiting_approval':
            raise SessionError('当前运行已结束或正在等待审批。')
        if len(state['steering']) >= 50 and not previous:
            raise SessionError('单次运行最多接收 50 条引导。')
        state['steering'][mid] = {'content': content, 'status': 'queued'}
        return {'id': mid, 'status': 'queued', 'run_id': run['id']}
    result = await io(storage.mutate, owner, key, 'steering_queued', enqueue)
    if result['status'] == 'queued':
        try:
            deliver(result['run_id'], owner, key, mid, content)
        except ValueError as cause:
            raise SessionError(str(cause)) from cause
    return result


def apply_steering(state, event, content):
    run = current(state)
    mid, old_id = event['id'], run['response_id']
    pending = state['steering'].get(mid)
    if not pending or pending['status'] != 'queued':
        raise SessionError('引导消息状态不一致。')
    old = state['nodes'][old_id]
    removed = not content.strip() and not old.get('context', {}).get('tool_calls') and not old.get('context', {}).get('file_changes') and not old.get('context', {}).get('reasoning')
    if removed:
        state['active_path'].pop()
        del state['nodes'][old_id]
    else:
        old.update(content=content, status='complete')
    message = {'id': mid, 'role': 'user', 'content': pending['content'], 'status': 'complete', 'context': {**{k: v for k, v in old['context'].items() if k not in ('tool_calls', 'file_changes', 'reasoning', 'execution_order', 'usage', 'execution_run_id', 'memory_sources')}, 'steering_status': 'applied', 'steering_run_id': run['id']}, 'created_at': now()}
    reply = {**message, 'id': mid + '-reply', 'role': 'assistant', 'content': '', 'status': 'streaming'}
    reply['context'] = {**message['context'], 'execution_run_id': run['id']}
    reply['context']['memory_sources'] = copy.deepcopy(old.get('context', {}).get('memory_sources', []))
    state['nodes'][mid] = {**message, 'parentId': state['active_path'][-1] if state['active_path'] else None}
    state['nodes'][reply['id']] = {**reply, 'parentId': mid}
    state['active_path'].extend([mid, reply['id']])
    run['response_id'] = reply['id']
    from ..harness.recovery import digest
    run['history_signature'] = digest([(key, state['nodes'][key]['content']) for key in state['active_path'][:-1]])
    pending['status'] = 'applied'
    touch(state)
    return {'type': 'steering', 'id': mid, 'response_id': reply['id'], 'previous_response_id': old_id,
            'previous_content': content, 'previous_removed': removed, 'message': {**message, 'seq': 0},
            'response': {**reply, 'seq': 0}, 'thread': detail(state)['thread']}


async def open_chat(params, rpc_state, resume=False):
    """先领取本地运行，再返回已持久化事件流。"""
    from ..transport.handlers import agent_chat, EventStream, AgentInput
    owner, key, body = params['owner_id'], params['thread_id'], params['body']
    await recover(owner, key)
    run_id = str(uuid4())
    # 模型参数在领取运行前校验，避免配置错误残留运行锁。
    from ..providers.settings import RuntimeConfig
    from ..agents.agent import settings_for
    from ..providers import local_settings
    runtime = RuntimeConfig.model_validate(params['runtime']) if params.get('runtime') else await io(local_settings.runtime, owner, 'model')
    settings = runtime.llm() if runtime else settings_for(body.get('model'))
    if body.get('model') and body['model'] != settings.model:
        raise SessionError('所选模型未配置。', 400)
    def begin(state):
        nonlocal run_id
        require(state)
        answers = None
        prefix = ''
        progress = ''
        memories = {'context': '', 'sources': []}
        if resume == 'checkpoint':
            if type(body.get('expected_revision')) is not int:
                raise SessionError('恢复请求缺少会话版本，请重新加载。', 400)
            unlocked(state, body.get('expected_revision'))
            run = state['runs'].get(body.get('run_id'))
            if not run or not run.get('recoverable') or run['response_id'] != state['active_path'][-1]:
                raise SessionError('原任务不可恢复或会话分支已变化，请重新加载。')
            from ..harness.recovery import digest, has_checkpoint
            if not has_checkpoint(run['id']):
                raise SessionError('执行检查点不存在，无法恢复原任务。')
            if run.get('project_id') != state['thread'].get('project_id') or run.get('history_signature') != digest([(mid, state['nodes'][mid]['content']) for mid in state['active_path'][:-1]]):
                raise SessionError('原任务的会话内容或工作目录已变化，请发送新消息继续。')
            if run['model'] != settings.model:
                raise SessionError('运行使用的模型配置已变化，请恢复原模型后重试。')
            run_id = run['id']
            run['last_resume_instruction'] = str(body.get('instruction', '接着执行'))[:128]
            prefix = state['nodes'][run['response_id']]['content']
            state['nodes'][run['response_id']]['status'] = 'streaming'
            state['knowledge_base_ids'] = run.get('knowledge_base_ids', [])
            run.update(status='running', recoverable=False, finished_at=None, error_code=None, error_message=None, deadline_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
            state['run_id'] = run_id
            touch(state)
            history = [{'role':'user', 'content':'继续原任务。'}]
        elif resume:
            approval = state['approvals'].get(body['approval_id'])
            run = current(state)
            if not approval or not run or approval['run_id'] != run['id'] or not approval['actionable'] or approval['status'] != 'pending':
                raise SessionError('审批已处理、停止或过期。')
            if run['model'] != settings.model:
                raise SessionError('运行使用的模型配置已变化，请恢复原模型后重试。')
            run_id = run['id']
            decision = body['decision']
            if decision not in ('approve', 'reject'):
                raise SessionError('审批决定无效。', 400)
            approval.update(status='approved' if decision == 'approve' else 'rejected', actionable=False, decided_at=now())
            answers = {item['id']: {'decisions': [{'type': decision} for _ in item['value']['action_requests']]} for item in approval['interrupts']}
            prefix = state['nodes'][run['response_id']]['content']
            state['nodes'][run['response_id']]['status'] = 'streaming'
            run['deadline_at'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
            history = [{'role': 'user', 'content': '继续处理工具审批。'}]
        else:
            unlocked(state, body['expected_revision'])
            path = state['active_path']
            if body['thread_id'] != key or len(path) < 2 or path[-1] != body['response_id']:
                raise SessionError('会话消息已变化，请重新加载。')
            reply = state['nodes'][path[-1]]
            if reply['role'] != 'assistant' or reply['status'] != 'streaming' or state['nodes'][path[-2]]['role'] != 'user':
                raise SessionError('消息无法重新执行。')
            from ..harness.recovery import digest
            run = {'history_signature': digest([(mid, state['nodes'][mid]['content']) for mid in path[:-1]]),
                   'knowledge_base_ids':body.get('knowledge_base_ids', state['knowledge_base_ids']),
                   'id': run_id, 'conversation_id': key, 'agent_id': state['thread']['agent_id'], 'response_id': body['response_id'],
                   'request_message_id': path[-2], 'project_id': state['thread'].get('project_id'),
                   'status': 'running', 'model': settings.model, 'error_code': None, 'error_message': None,
                   'started_at': now(), 'deadline_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), 'finished_at': None}
            from .images import model_images
            message_path = path[:-1][-100:]
            if sum(len(state['nodes'][mid].get('context', {}).get('images', [])) for mid in message_path if state['nodes'][mid]['role'] == 'user') > 5:
                raise SessionError('会话图片上下文过大，请新建会话。', 400)
            history = [{'role': state['nodes'][mid]['role'], 'content': state['nodes'][mid]['content'],
                        'images': model_images(owner, state['nodes'][mid].get('context', {}).get('images', [])) if state['nodes'][mid]['role'] == 'user' else []}
                       for mid in message_path if state['nodes'][mid]['content'] and (state['nodes'][mid]['role'] == 'user' or state['nodes'][mid]['status'] == 'complete')]
            from .progress import execution_context
            progress = execution_context(state, path[:-1], history)
            reply.setdefault('context', {})['execution_run_id'] = run_id
            state['runs'][run_id] = run
            state['run_id'] = run_id
        if resume != 'checkpoint':
            state['knowledge_base_ids'] = body.get('knowledge_base_ids', state['knowledge_base_ids'])
        payload = {'agent_code': {1: 'general', 2: 'product', 3: 'ui'}[state['thread']['agent_id']], 'thread_id': key,
                   'messages': history[-100:], 'model': settings.model, 'run_id': run_id,
                   'execution_context': progress,
                   'memory_context': memories['context'],
                   'workspace_owner_id': owner, 'project_id': state['thread']['project_id'],
                   'knowledge_base_ids': state['knowledge_base_ids'],
                   'checkpoint_resume': resume == 'checkpoint',
                   'runtime': runtime, 'retrieval_token': params.get('retrieval_token'), 'approval_resume': answers}
        # 校验模型输入大小等限制后再提交运行。
        AgentInput.model_validate(payload)
        return payload, prefix
    task = asyncio.current_task()
    # 在 SQLite 提交前注册任务，读取方不会误判刚启动的运行已失联。
    original_begin = begin
    def begin_registered(state):
        for previous_id in state.get('runs', {}):
            previous = ACTIVE.get((owner, previous_id))
            if previous is not None and previous is not task and not previous.done():
                raise SessionError('上一轮仍在停止和保存进度，请稍后再发送。')
        if state.get('thread', {}).get('project_id'):
            from .projects import get
            get(owner, state['thread']['project_id'])
        result = original_begin(state)
        ACTIVE[owner, run_id] = task
        return result
    try:
        payload, prefix = await io(storage.mutate, owner, key, 'run_resumed' if resume == 'checkpoint' else 'approval_decided' if resume else 'run_started', begin_registered)
    except BaseException:
        ACTIVE.pop((owner, run_id), None)
        raise
    try:
        if not resume:
            from ..memory.service import semantic_recall
            memories = await semantic_recall(
                owner, payload['agent_code'], payload['project_id'],
                next((row['content'] for row in reversed(payload['messages']) if row['role'] == 'user'), ''),
                max(0, 120000 - sum(len(row['content']) for row in payload['messages']) - len(payload['execution_context'])),
                storage.root)
            payload['memory_context'] = memories['context']
            def save_memory_sources(state):
                run = current(state)
                if not run or run['id'] != run_id or run['status'] != 'running':
                    raise SessionError('运行已停止。')
                state['nodes'][run['response_id']].setdefault('context', {})['memory_sources'] = memories['sources']
            await io(storage.mutate, owner, key, 'memory_recalled', save_memory_sources)
        upstream = await agent_chat(payload, rpc_state)
    except BaseException:
        ACTIVE.pop((owner, run_id), None)
        await io(storage.mutate, owner, key, 'run_failed', lambda s: finish(s, 'failed', 'AGENT_CONNECT_FAILED', '执行启动失败。'))
        raise
    async def close_unstarted():
        # async generator 从未迭代时，aclose 不会执行它的 finally。
        if ACTIVE.get((owner, run_id)) is asyncio.current_task():
            try:
                await upstream.aclose()
                await io(storage.mutate, owner, key, 'run_cancelled',
                         lambda state: finish(state, 'cancelled', 'CLIENT_DISCONNECTED', '客户端已停止或断开连接。'))
            finally:
                ACTIVE.pop((owner, run_id), None)
    return EventStream(persist_events(owner, key, run_id, upstream.events, prefix), on_close=close_unstarted)


async def persist_events(owner, key, run_id, events, prefix=''):
    """清理和进度落盘结束前保留活动登记，避免新旧运行重叠。"""
    stream = _persist_events(owner, key, run_id, events, prefix)
    try:
        async for event in stream:
            yield event
    finally:
        try:
            await stream.aclose()
        finally:
            if ACTIVE.get((owner, run_id)) is asyncio.current_task():
                ACTIVE.pop((owner, run_id), None)


async def _persist_events(owner, key, run_id, events, prefix=''):
    """正文按秒合并落盘；工具、审批和终态先保存再通知界面。"""
    content, last_save, terminal = prefix, time.monotonic(), False
    thoughts, order = [], []
    try:
        initial = await io(storage.get, owner, key)
        context = initial['nodes'][initial['runs'][run_id]['response_id']].get('context', {})
        thoughts = copy.deepcopy(context.get('reasoning', []))
        order = list(context.get('execution_order', []))
        async with asyncio.timeout(600):
            async for event in events:
                kind = event.get('type')
                if kind in ('reasoning', 'reasoning_end'):
                    thought = next((item for item in thoughts if item['id'] == event['id']), None)
                    if thought is None:
                        thought = {'id': event['id'], 'text': '', 'started_at': round(time.time() * 1000)}
                        thoughts.append(thought)
                        order.append('reasoning:' + thought['id'])
                    if kind == 'reasoning': thought['text'] += event.get('text', '')
                    else: thought['completed_at'] = round(time.time() * 1000)
                    if sum(len(item['text']) for item in thoughts) > 120000:
                        raise SessionError('模型思考内容过长，请简化任务。')
                    event = {**event, 'started_at': thought['started_at'], **({'completed_at': thought['completed_at']} if 'completed_at' in thought else {})}
                if kind == 'tool_call' and 'tool:' + event['id'] not in order:
                    order.append('tool:' + event['id'])
                if kind == 'restore':
                    content = event['content']
                    prefix = ''
                if kind == 'delta':
                    content += event.get('text', '')
                    if len(content) > 120000:
                        raise SessionError('回答过长，请简化任务。')
                if kind == 'done':
                    if not isinstance(event.get('content'), str) or not event['content'].strip():
                        raise SessionError('模型返回了空回答。')
                    content = prefix + event['content']
                    event = {**event, 'content': content}
                save = kind not in ('delta', 'reasoning') or time.monotonic() - last_save >= 1
                if save:
                    def persist(state):
                        run = current(state)
                        if not run or run['id'] != run_id or run['status'] != 'running':
                            raise SessionError('运行已停止。')
                        reply = state['nodes'][run['response_id']]
                        reply['content'] = content[:120000]
                        reply.setdefault('context', {}).update(reasoning=copy.deepcopy(thoughts), execution_order=list(order))
                        if kind == 'compaction':
                            reply['context']['compaction'] = {k: event[k] for k in ('id', 'status')}
                        if kind == 'usage':
                            run['usage'] = copy.deepcopy(event['usage'])
                            reply['context']['usage'] = copy.deepcopy(event['usage'])
                        if kind == 'file_change':
                            reply.setdefault('context', {}).setdefault('file_changes', []).append(event['change'])
                        if kind in ('tool_call', 'tool_result'):
                            return record_tool(reply, event)
                        if kind == 'steering':
                            return apply_steering(state, event, content)
                        if kind == 'approval':
                            interrupts = event['interrupts']
                            if not interrupts or len(interrupts) > 16:
                                raise SessionError('审批数据无效。')
                            aid = str(uuid4())
                            state['approvals'][aid] = {'id': aid, 'run_id': run_id, 'conversation_id': key,
                                'response_id': run['response_id'], 'status': 'pending', 'interrupts': interrupts,
                                'actionable': True, 'created_at': now(), 'decided_at': None}
                            reply['status'] = 'waiting_approval'
                            run['deadline_at'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                            touch(state)
                            return {**event, 'approval_id': aid}
                        if kind == 'done':
                            reply['status'] = 'complete'
                            state['thread']['draft'] = ''
                            finish(state, 'completed')
                        elif kind == 'error':
                            reply['content'] = content or event.get('message', '执行失败。')
                            finish(state, 'failed', event.get('code', 'AGENT_FAILED'), event.get('message', '执行失败。'))
                        return event
                    # 流式正文已在 patch 中，不重复写 token；其余执行事件保留原始事件。
                    event = await io(storage.mutate, owner, key, 'agent_event', persist,
                                     {k: v for k, v in event.items() if k not in ('content', 'text')} if kind in ('delta', 'reasoning') else event)
                    last_save = time.monotonic()
                if kind == 'steering':
                    content = prefix = ''
                    thoughts, order = [], []
                if kind in ('done', 'error', 'approval'):
                    terminal = True
                yield {**event, 'run_id': run_id}
                if terminal:
                    return
    except asyncio.CancelledError:
        raise
    except Exception as cause:
        terminal = True
        def fail(state):
            run = current(state)
            if run and run['id'] == run_id:
                state['nodes'][run['response_id']]['content'] = content[:120000]
                state['nodes'][run['response_id']].setdefault('context', {}).update(reasoning=copy.deepcopy(thoughts), execution_order=list(order))
                finish(state, 'failed', 'AGENT_FAILED', str(cause)[:300] if isinstance(cause, SessionError) else '执行异常，请重试。')
        await io(storage.mutate, owner, key, 'run_failed', fail)
        yield {'type': 'error', 'run_id': run_id, 'code': 'AGENT_FAILED', 'message': str(cause) if isinstance(cause, SessionError) else '执行异常，请重试。'}
    finally:
        try:
            await events.aclose()
        finally:
            if not terminal:
                def stop(state):
                    run = state['runs'].get(run_id)
                    if run and (state['run_id'] in (None, run_id)):
                        reconcile_files(owner, state, run)
                        reply = state['nodes'].get(run['response_id'])
                        if reply and run['status'] in ('running', 'cancelled'):
                            reply['content'] = content[:120000]
                            reply.setdefault('context', {}).update(reasoning=copy.deepcopy(thoughts), execution_order=list(order))
                            from .execution import finish_tools
                            finish_tools(reply)
                        if run['status'] == 'running':
                            finish(state, 'cancelled', 'CLIENT_DISCONNECTED', '客户端已停止或断开连接。')
                await io(storage.mutate, owner, key, 'run_cancelled', stop)
            def settle_usage(state):
                run = state.get('runs', {}).get(run_id)
                if run:
                    reconcile_usage(state, run)
                    return run['status'] == 'completed'
                return False
            settled = await io(storage.mutate, owner, key, 'run_usage_saved', settle_usage)
            if settled:
                from ..harness.usage import usage_path
                await io(usage_path(run_id).unlink, True)
