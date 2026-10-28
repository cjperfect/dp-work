"""会话权限、版本控制、迁移及流式回答保存。"""
import codecs
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import anyio
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from .conversation_models import Conversation, ConversationMessage
from .conversation_repository import ConversationRepository
from .schemas import AgentRequest
from .run_models import AgentRun
from . import run_service
from .run_control import RunControl, RunStopped


def missing():
    """对不存在和无权访问的会话返回相同错误。"""
    return ApiError(ApiCode.NOT_FOUND, '会话不存在。', 404)


def metadata(row):
    """返回列表字段，不暴露执行令牌。"""
    return {key: getattr(row, key) for key in ('id', 'agent_id', 'project_id', 'title', 'title_source', 'draft', 'draft_revision', 'created_at', 'updated_at')}


def check_revision(row, expected):
    """生成期间禁止改写消息；旧页面不得覆盖新版本。"""
    if row.run_token and row.run_until and row.run_until > datetime.now(timezone.utc):
        raise ApiError(ApiCode.STATE_CONFLICT, '该会话正在生成回答，请先停止或稍后重试。', 409)
    if row.draft_revision != expected:
        raise ApiError(ApiCode.STATE_CONFLICT, '会话已在其他页面更新，请重新加载。', 409)


async def expire_run(db, row):
    """服务异常退出后把过期生成标记为中断。"""
    expired = row.run_token and (row.run_until is None or row.run_until <= datetime.now(timezone.utc))
    if expired or not row.run_token:
        messages = await ConversationRepository(db).messages(row.id)
        if not expired and not any(message.status in ('streaming', 'waiting_approval') for message in messages): return
        for message in messages:
            if message.status in ('streaming', 'waiting_approval'):
                message.status = 'failed'
                message.content = message.content or '生成中断，请重试。'
        await run_service.finish_locked(db, row, 'interrupted', 'RUN_EXPIRED', '执行中断，请重试。')
        row.run_token = row.run_until = None
        row.draft_revision += 1
        await db.flush()


async def detail(db, row):
    """根据选中路径恢复消息，同时返回全部分支。"""
    nodes = await ConversationRepository(db).messages(row.id)
    def serialize(message, seq=0):
        return {'id': message.id, 'role': message.role, 'seq': seq, 'content': message.content,
            'status': message.status, 'context': message.context, 'created_at': message.created_at}
    by_id = {message.id: message for message in nodes}
    return {'thread': metadata(row), 'knowledge_base_ids': row.knowledge_base_ids,
        'messages': [serialize(by_id[key], index + 1) for index, key in enumerate(row.active_path) if key in by_id],
        'message_branches': [{'parentId': message.parent_id, 'message': serialize(message)} for message in nodes]}


async def list_threads(owner, q='', agent_id=None):
    """查询账号下全部 Agent 的会话元数据。"""
    async with session.read_session() as db:
        return [{**dict(row), "draft": ""} for row in await ConversationRepository(db).list(owner, q, agent_id)]


async def create(owner, body):
    """按客户端请求 ID 幂等创建会话。"""
    async with session.transaction() as db:
        if body.project_id:
            from .project_service import owned
            await owned(db, owner, body.project_id, True)
        await db.execute(insert(Conversation).values(id=body.id, owner_id=owner, agent_id=body.agent_id,
            knowledge_base_ids=body.knowledge_base_ids, project_id=body.project_id).on_conflict_do_nothing(index_elements=[Conversation.id]))
        row = await ConversationRepository(db).get(owner, body.id, lock=True)
        if row is None: raise missing()
        if row.agent_id != body.agent_id or row.project_id != body.project_id:
            raise ApiError(ApiCode.STATE_CONFLICT, '会话与 Agent 不匹配。', 409)
        return await detail(db, row)


async def get(owner, key):
    """读取本人会话并恢复异常中断状态。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None: raise missing()
        await expire_run(db, row)
        return await detail(db, row)


async def save_draft(owner, key, body):
    """只更新草稿和上下文选择，不反复发送整段历史。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None: raise missing()
        if row.run_token: await expire_run(db, row)
        check_revision(row, body.expected_revision)
        row.draft, row.knowledge_base_ids = body.draft, body.knowledge_base_ids
        row.draft_revision += 1
        await db.flush()
        return metadata(row)


async def write_graph(db, row, body, importing=False):
    """合并消息节点，历史分支不因切换选中路径而丢失。"""
    entries = {entry.message.id: entry for entry in body.message_branches}
    from .conversation_schemas import BranchIn
    for index, message in enumerate(body.messages):
        entries[message.id] = BranchIn(parentId=body.messages[index - 1].id if index else None, message=message)
    existing = {message.id: message for message in await ConversationRepository(db).messages(row.id)}
    total_content = sum(len(entry.message.content) + len(str(entry.message.context)) for entry in entries.values()) + sum(len(message.content) + len(str(message.context)) for key, message in existing.items() if key not in entries)
    if len(set(existing) | set(entries)) > 5000 or total_content > 4000000:
        raise ApiError(ApiCode.PARAM_ERROR, '会话分支过多，请新建会话。', 400)
    values = []
    for entry in entries.values():
        message = entry.message
        previous = existing.get(message.id)
        if previous and (previous.parent_id != entry.parentId or previous.role != message.role):
            raise ApiError(ApiCode.STATE_CONFLICT, '消息节点归属不可更改。', 409)
        values.append({'conversation_id': row.id, 'id': message.id, 'parent_id': entry.parentId,
            'role': message.role, 'content': message.content,
            'status': 'cancelled' if importing and message.status == 'streaming' else message.status,
            'context': message.context, 'created_at': message.created_at})
    for start in range(0, len(values), 256):
        statement = insert(ConversationMessage).values(values[start:start + 256])
        await db.execute(statement.on_conflict_do_update(index_elements=[ConversationMessage.conversation_id, ConversationMessage.id],
            set_={key: getattr(statement.excluded, key) for key in ('content', 'status', 'context')}))
    row.active_path = [message.id for message in body.messages]
    row.draft_revision += 1
    row.updated_at = func.clock_timestamp()
    await db.flush()


async def save_graph(owner, key, body):
    """乐观锁保存消息和当前分支，拒绝已删除会话重建。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None: raise missing()
        if row.run_token: await expire_run(db, row)
        check_revision(row, body.expected_revision)
        await write_graph(db, row, body)
        await db.refresh(row)
        return await detail(db, row)


async def rename(owner, key, body):
    """人工重命名优先；延迟生成标题不能覆盖人工标题或新的首条消息。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None: raise missing()
        if body.title_source == 'manual' or (row.title_source == 'pending' and row.active_path and row.active_path[0] == body.first_message_id):
            row.title = body.title.strip()
            if not row.title: raise ApiError(ApiCode.PARAM_ERROR, '请输入会话标题。', 400)
            row.title_source = body.title_source
            row.updated_at = func.clock_timestamp()
        await db.flush()
        await db.refresh(row)
        return metadata(row)


async def remove(owner, key):
    """删除全部消息，保留无正文的 ID 墓碑阻止旧保存和旧迁移复活。"""
    async with session.transaction() as db:
        repository = ConversationRepository(db)
        row = await repository.get(owner, key, lock=True, deleted=True)
        if row is None: raise missing()
        await run_service.stop_locked(db, row, 'cancelled', 'CONVERSATION_DELETED', '会话已删除。')
        await repository.clear_messages(key)
        row.deleted_at = func.now()
        row.title, row.draft, row.active_path, row.knowledge_base_ids = '已删除', '', [], []
        row.run_token = row.run_until = None


async def import_thread(owner, body):
    """只迁入不存在的本地会话，服务端已有记录始终优先。"""
    async with session.transaction() as db:
        inserted = await db.scalar(insert(Conversation).values(id=body.thread.id, owner_id=owner,
            agent_id=body.thread.agent_id, title=body.thread.title, title_source=body.thread.title_source,
            draft=body.thread.draft, knowledge_base_ids=body.knowledge_base_ids,
            created_at=body.thread.created_at, updated_at=body.thread.updated_at).on_conflict_do_nothing(
                index_elements=[Conversation.id]).returning(Conversation.id))
        row = await ConversationRepository(db).get(owner, body.thread.id, lock=True, deleted=True)
        if row is None: raise missing()
        if row.deleted_at: return None
        if inserted:
            await write_graph(db, row, body, importing=True)
            row.updated_at = body.thread.updated_at
        return await detail(db, row)


async def begin_chat(owner, key, body):
    """从 PG 当前路径构造模型上下文，客户端不能替换历史或 Agent 归属。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None: raise missing()
        if row.run_token: await expire_run(db, row)
        check_revision(row, body.expected_revision)
        if body.thread_id != key or len(row.active_path) < 2 or row.active_path[-1] != body.response_id:
            raise ApiError(ApiCode.STATE_CONFLICT, '会话消息已变化，请重新加载。', 409)
        nodes = {message.id: message for message in await ConversationRepository(db).messages(key)}
        reply = nodes.get(body.response_id)
        if not reply or reply.role != 'assistant' or reply.status != 'streaming' or nodes[row.active_path[-2]].role != 'user':
            raise ApiError(ApiCode.STATE_CONFLICT, '消息无法重新执行。', 409)
        token = str(uuid4())
        row.run_token, row.run_until = token, datetime.now(timezone.utc) + timedelta(seconds=config.AGENT_REQUEST_TIMEOUT + 60)
        history = [{'role': nodes[mid].role, 'content': nodes[mid].content} for mid in row.active_path[:-1]
            if nodes[mid].content and (nodes[mid].role == 'user' or nodes[mid].status == 'complete')]
        payload = AgentRequest(agent_code='general' if row.agent_id == 1 else 'product', thread_id=key,
            messages=history[-100:], knowledge_base_ids=body.knowledge_base_ids, model=body.model, project_id=row.project_id)
        from src.infrastructure.sidecar.context import scope
        db.add(AgentRun(device_id=scope.get()[1], id=token, owner_id=owner, conversation_id=key, agent_id=row.agent_id,
            response_id=body.response_id, model=body.model, status='running',
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=config.AGENT_REQUEST_TIMEOUT)))
        return token, payload


async def save_reply(owner, key, response_id, token, content, status, code=None, error=None, model=None):
    """仅当前执行器可保存回答，终态提交后再向浏览器发送 done。"""
    async with session.transaction() as db:
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if row is None or row.run_token != token: return False
        run = await db.get(AgentRun, token, with_for_update=True)
        if run and (run.status != 'running' or run.deadline_at <= datetime.now(timezone.utc)):
            if run.status == 'running':
                await run_service.stop_locked(db, row, 'interrupted', 'RUN_EXPIRED', '运行超时或执行服务中断，请重试。')
            return False
        message = await db.get(ConversationMessage, (key, response_id))
        if message is None: return False
        message.content, message.status = content[:120000], status
        if run and model: run.model = model[:128]
        if status != 'streaming':
            await run_service.finish_locked(db, row,
                'completed' if status == 'complete' else status, code, error)
            row.run_token = row.run_until = None
            if status == 'complete': row.draft = ''
            row.draft_revision += 1
            row.updated_at = func.clock_timestamp()
        return True


async def open_chat(owner, key, body):
    """在领取运行前固定执行设备，审批恢复不能漂移到另一台设备。"""
    if config.SIDECAR_TRANSPORT == 'device':
        from src.infrastructure.sidecar.context import scope, execution_scope
        from src.infrastructure.sidecar.relay import online_device, DeviceOffline
        target = scope.get()[1]
        async with session.read_session() as db:
            thread = await ConversationRepository(db).get(owner, key)
            if thread and thread.project_id:
                from .project_service import owned
                project = await owned(db, owner, thread.project_id)
                if target and target != project.device_id:
                    raise ApiError(ApiCode.STATE_CONFLICT, '该项目属于另一台设备，请在对应桌面端打开。', 409)
                target = project.device_id
        try:
            device = await online_device(owner, target)
        except DeviceOffline as cause:
            raise ApiError(ApiCode.INTERNAL_ERROR, '本机执行设备未连接。', 503) from cause
        with execution_scope(owner, device.id):
            return await _open_chat(owner, key, body)
    return await _open_chat(owner, key, body)


async def _open_chat(owner, key, body):
    """领取生成租约，并在连接上游失败时保存失败状态。"""
    from . import service
    token, payload = await begin_chat(owner, key, body)
    control = RunControl(token)
    try:
        await control.open()
        upstream = await control.wait(service.open_chat(payload, owner, run_id=token))
    except BaseException as cause:
        with anyio.CancelScope(shield=True):
            cancelled = isinstance(cause, asyncio.CancelledError)
            await save_reply(owner, key, body.response_id, token, '', 'cancelled' if cancelled else 'failed',
                'CLIENT_DISCONNECTED' if cancelled else 'AGENT_CONNECT_FAILED',
                '客户端已断开。' if cancelled else '无法连接 Agent 执行服务，请重试。')
            await control.close()
        if isinstance(cause, RunStopped):
            raise ApiError(ApiCode.STATE_CONFLICT, '运行已停止或中断。', 409) from cause
        raise
    return StoredStream(owner, key, body.response_id, token, upstream, control, payload.knowledge_base_ids)


class StoredStream:
    """包装 SSE，按秒保存增量，结束和取消保存最终状态。"""
    def __init__(self, owner, key, response_id, token, upstream, control, knowledge_base_ids=None):
        self.owner, self.key, self.response_id, self.token, self.upstream = owner, key, response_id, token, upstream
        self.content, self.status = '', 'streaming'
        self.prefix = ''
        self.knowledge_base_ids = knowledge_base_ids or []
        self.finished = False
        self.control = control

    async def persist(self, status, code=None, error=None, model=None):
        """在请求取消时仍允许完成本地事务。"""
        with anyio.CancelScope(shield=True):
            saved = await save_reply(self.owner, self.key, self.response_id, self.token, self.content, status, code, error, model)
        if status != 'streaming': self.finished = True
        if not saved: raise RunStopped()

    async def close(self):
        """断开上游，并保留已经生成的回答。"""
        try:
            if not self.finished:
                try:
                    await self.persist('cancelled', 'CLIENT_DISCONNECTED', '客户端已停止或断开连接。')
                except RunStopped:
                    self.finished = True
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await self.upstream.close()
                finally:
                    await self.control.close()

    async def chunks(self):
        """先提交最终回答，再转发完成事件。"""
        decoder, buffer, last_save = codecs.getincrementaldecoder('utf-8')(), '', time.monotonic()
        try:
            iterator = self.upstream.chunks().__aiter__()
            while True:
                try:
                    chunk = await self.control.wait(anext(iterator))
                except StopAsyncIteration:
                    break
                buffer += decoder.decode(chunk)
                buffer = buffer.replace('\r\n', '\n')
                if len(buffer) > 2000000: raise ValueError('event too large')
                while '\n\n' in buffer:
                    frame, buffer = buffer.split('\n\n', 1)
                    data = '\n'.join(line[5:].lstrip() for line in frame.splitlines() if line.startswith('data:'))
                    if data:
                        event = json.loads(data)
                        event['run_id'] = self.token
                        if event.get('type') == 'start':
                            await self.persist('streaming', model=event.get('model'))
                        if event.get('type') == 'delta': self.content += event.get('text', '')
                        if len(self.content) > 120000: raise ValueError('reply too large')
                        if event.get('type') == 'approval':
                            from .approval_service import pause
                            await self.persist('streaming')
                            event['approval_id'] = await pause(self.owner, self.key, self.token,
                                event.get('interrupts'), self.knowledge_base_ids)
                            self.finished = True
                        elif event.get('type') == 'done':
                            if not isinstance(event.get('content'), str) or not event['content'].strip() or len(event['content']) > 120000:
                                raise ValueError('invalid final reply')
                            self.content = self.prefix + event['content']
                            if len(self.content) > 120000: raise ValueError('reply too large')
                            event['content'] = self.content
                            await self.persist('complete', model=event.get('model'))
                        elif event.get('type') == 'error':
                            self.content = self.content or event.get('message', '生成失败，请重试。')
                            await self.persist('failed', str(event.get('code') or 'AGENT_FAILED')[:64],
                                str(event.get('message') or 'Agent 执行失败，请重试。')[:300])
                        elif time.monotonic() - last_save >= 1:
                            await self.persist('streaming')
                            last_save = time.monotonic()
                        frame = 'data: ' + json.dumps(event, ensure_ascii=False, separators=(',', ':'))
                    yield (frame + '\n\n').encode()
                    if self.finished: return
                if self.finished: return
            if not self.finished:
                await self.persist('failed', 'AGENT_DISCONNECTED', 'Agent 回答中断，请重试。')
                yield ('data: ' + json.dumps({'type': 'error', 'run_id': self.token,
                    'code': 'AGENT_DISCONNECTED', 'message': 'Agent 回答中断，请重试。'}) + '\n\n').encode()
        except RunStopped:
            with anyio.CancelScope(shield=True):
                await save_reply(self.owner, self.key, self.response_id, self.token, self.content,
                    'failed', 'RUN_CONTROL_LOST', '运行已停止或中断。')
            self.finished = True
            yield ('data: ' + json.dumps({'type': 'error', 'run_id': self.token,
                'code': 'RUN_STOPPED', 'message': '运行已停止或中断。'}) + '\n\n').encode()
        except (ValueError, KeyError, TypeError):
            await self.persist('failed', 'INVALID_AGENT_EVENT', 'Agent 返回了无效的回答，请重试。')
            yield ('data: ' + json.dumps({'type': 'error', 'run_id': self.token,
                'code': 'INVALID_AGENT_EVENT', 'message': 'Agent 返回了无效的回答，请重试。'}) + '\n\n').encode()
        finally:
            await self.close()
