"""持久化待审批操作，并将用户的一次性决定恢复到原执行设备。"""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.infrastructure.sidecar.context import execution_scope
from .approval_models import AgentApproval
from .conversation_models import Conversation, ConversationMessage
from .run_models import AgentRun
from .run_control import RunControl, RunStopped
from .schemas import AgentRequest


def serialize(row, run):
    """返回审批内容与可操作状态，不返回内部恢复凭证。"""
    return {"id": row.id, "run_id": row.run_id, "conversation_id": run.conversation_id,
            "response_id": run.response_id, "status": row.status, "interrupts": row.interrupts,
            "actionable": row.status == 'pending' and run.status == 'running' and run.deadline_at > datetime.now(timezone.utc),
            "created_at": row.created_at, "decided_at": row.decided_at}


async def list_approvals(owner, conversation_id):
    """读取当前用户会话的审批记录。"""
    async with session.read_session() as db:
        rows = (await db.execute(select(AgentApproval, AgentRun).join(AgentRun).join(Conversation)
            .where(AgentRun.owner_id == owner, Conversation.deleted_at.is_(None),
                   AgentRun.conversation_id == conversation_id)
            .order_by(AgentApproval.created_at.desc()).limit(20))).all()
        return [serialize(row, run) for row, run in reversed(rows)]


async def pause(owner, key, run_id, interrupts, knowledge_base_ids):
    """先保存审批并延长等待期限，再让前端接收暂停事件。"""
    if not isinstance(interrupts, list) or not interrupts or len(interrupts) > 16 or len(json.dumps(interrupts)) > 1000000:
        raise ValueError('invalid approval payload')
    for item in interrupts:
        if not isinstance(item, dict) or not isinstance(item.get('value'), dict):
            raise ValueError('invalid interrupt')
        if not isinstance(item.get('id'), str) or not item['id'] or len(item['id']) > 128:
            raise ValueError('invalid interrupt id')
        actions = item.get('value', {}).get('action_requests', [])
        if not isinstance(actions, list) or not actions or len(actions) > 16 or any(not isinstance(action, dict) or action.get('name') not in ('write_file', 'edit_file', 'execute') or not isinstance(action.get('args'), dict) for action in actions):
            raise ValueError('invalid approval action')
    if len({item['id'] for item in interrupts}) != len(interrupts):
        raise ValueError('duplicate interrupt ids')
    approval_id = str(uuid5(NAMESPACE_URL, run_id + ':' + ':'.join(sorted(item['id'] for item in interrupts))))
    async with session.transaction() as db:
        thread = await db.get(Conversation, key, with_for_update=True)
        if not thread or thread.owner_id != owner or thread.run_token != run_id:
            raise RunStopped()
        run = await db.get(AgentRun, run_id, with_for_update=True)
        if run is None or run.status != 'running' or run.deadline_at <= datetime.now(timezone.utc):
            raise RunStopped()
        existing = await db.get(AgentApproval, approval_id)
        if existing and existing.status != 'pending':
            raise RunStopped()
        if not existing:
            db.add(AgentApproval(id=approval_id, run_id=run_id, interrupts=interrupts,
                knowledge_base_ids=knowledge_base_ids, status='pending'))
            thread.draft = ''
            thread.draft_revision += 1
        reply = await db.get(ConversationMessage, (thread.id, run.response_id))
        if reply: reply.status = 'waiting_approval'
        run.deadline_at = datetime.now(timezone.utc) + timedelta(hours=24)
        thread.run_until = run.deadline_at
    return approval_id


async def decide(owner, approval_id, decision):
    """一次性领取审批，恢复同一运行；重复决定及其他用户请求均被拒绝。"""
    if decision not in ('approve', 'reject'):
        raise ApiError(ApiCode.PARAM_ERROR, '审批决定无效。', 400)
    async with session.read_session() as db:
        initial = (await db.execute(select(AgentRun.conversation_id).join(AgentApproval)
            .where(AgentApproval.id == approval_id, AgentRun.owner_id == owner))).scalar_one_or_none()
    if not initial:
        raise ApiError(ApiCode.NOT_FOUND, '审批不存在。', 404)
    async with session.transaction() as db:
        thread = await db.get(Conversation, initial, with_for_update=True)
        approval = await db.get(AgentApproval, approval_id)
        if not thread or not approval:
            raise ApiError(ApiCode.NOT_FOUND, '审批不存在。', 404)
        run = await db.get(AgentRun, approval.run_id, with_for_update=True)
        await db.refresh(approval, with_for_update=True)
        if (not thread or thread.deleted_at or thread.owner_id != owner or approval.status != 'pending'
                or run is None or run.status != 'running' or thread.run_token != run.id or run.deadline_at <= datetime.now(timezone.utc)):
            raise ApiError(ApiCode.STATE_CONFLICT, '审批已处理、停止或过期，请重新加载。', 409)
        approval.status = 'approved' if decision == 'approve' else 'rejected'
        approval.decided_at = datetime.now(timezone.utc)
        answers = {item['id']: {'decisions': [{'type': decision} for _ in item['value']['action_requests']]}
                   for item in approval.interrupts}
        run.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=config.AGENT_REQUEST_TIMEOUT + 60)
        thread.run_until = run.deadline_at
        reply = await db.get(ConversationMessage, (thread.id, run.response_id))
        prefix = reply.content if reply else ''
        if reply: reply.status = 'streaming'
        payload = AgentRequest(agent_code='general' if run.agent_id == 1 else 'product', thread_id=thread.id,
            messages=[{'role': 'user', 'content': '继续处理工具审批。'}],
            knowledge_base_ids=approval.knowledge_base_ids, model=run.model, project_id=thread.project_id)
        run_id, key, response_id, device_id = run.id, thread.id, run.response_id, run.device_id
    from . import service
    from .conversation_service import StoredStream, save_reply
    control = RunControl(run_id)
    try:
        await control.open()
        with execution_scope(owner, device_id):
            upstream = await control.wait(service.open_chat(payload, owner, run_id=run_id, approval_resume=answers))
    except BaseException:
        import anyio
        with anyio.CancelScope(shield=True):
            await save_reply(owner, key, response_id, run_id, prefix, 'failed', 'APPROVAL_RESUME_FAILED', '审批恢复失败，请检查原执行设备。')
            await control.close()
        raise
    stream = StoredStream(owner, key, response_id, run_id, upstream, control, payload.knowledge_base_ids)
    stream.content = stream.prefix = prefix
    return stream
