"""Agent 运行状态、用户取消和异常中断恢复。"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from src.core.exceptions import ApiError
from src.core.pagination import PageParams
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.infrastructure.database.pagination import paginate
from .conversation_models import Conversation, ConversationMessage
from .run_models import AgentRun

log = logging.getLogger(__name__)
FIELDS = ("id", "conversation_id", "agent_id", "response_id", "status", "model", "error_code",
          "error_message", "started_at", "deadline_at", "finished_at")


def serialize(row):
    """返回执行元数据，不暴露会话租约或模型凭证。"""
    return {key: getattr(row, key) for key in FIELDS}


async def finish_locked(db, thread, status, code=None, message=None):
    """会话锁内写入终态，迟到的模型结果不能覆盖已取消的运行。"""
    run = await db.get(AgentRun, thread.run_token, with_for_update=True) if thread.run_token else None
    if run and run.status == "running":
        run.status, run.error_code, run.error_message = status, code, message
        run.finished_at = func.clock_timestamp()
        await db.flush()
        await db.refresh(run, ["finished_at"])
        await db.execute(text("SELECT pg_notify('agent_runs', :payload)"),
                         {"payload": json.dumps({"run_id": run.id})})
    return run


async def stop_locked(db, thread, status, code, message):
    """停止当前运行并更新对应回复，保留已生成正文。"""
    run = await finish_locked(db, thread, status, code, message)
    if run:
        reply = await db.get(ConversationMessage, (thread.id, run.response_id))
        if reply and reply.status == "streaming":
            reply.status = "cancelled" if status == "cancelled" else "failed"
        thread.run_token = thread.run_until = None
        thread.draft_revision += 1
        thread.updated_at = func.clock_timestamp()
    return run


async def recover(run_id=None):
    """只收敛超过执行期限的运行，避免误停其他 API 实例的任务。"""
    async with session.read_session() as db:
        keys = (await db.execute(select(AgentRun.id, AgentRun.conversation_id).where(
            AgentRun.status == "running", AgentRun.deadline_at <= func.now(),
            *([AgentRun.id == run_id] if run_id else [])).limit(100))).all()
    for key, conversation_id in keys:
        async with session.transaction() as db:
            # 与保存、取消使用一致的锁顺序：会话 → 运行。
            thread = await db.get(Conversation, conversation_id, with_for_update=True)
            run = await db.get(AgentRun, key, with_for_update=True)
            if not run or run.status != "running" or run.deadline_at > datetime.now(timezone.utc):
                continue
            if thread and thread.run_token == key:
                await stop_locked(db, thread, "interrupted", "RUN_EXPIRED", "运行超时或执行服务中断，请重试。")
            else:
                run.status, run.error_code = "interrupted", "RUN_ORPHANED"
                run.error_message = "运行已失去会话执行权，请重试。"
                run.finished_at = func.clock_timestamp()
                await db.execute(text("SELECT pg_notify('agent_runs', :payload)"), {"payload": json.dumps({"run_id": key})})


def owned_query(owner):
    """隐藏其他用户及已删除会话的运行。"""
    return select(AgentRun).join(Conversation, Conversation.id == AgentRun.conversation_id).where(
        AgentRun.owner_id == owner, Conversation.owner_id == owner, Conversation.deleted_at.is_(None))


async def get(owner, run_id):
    """查询本人单次运行，按需收敛过期状态。"""
    async with session.read_session() as db:
        row = await db.scalar(owned_query(owner).where(AgentRun.id == run_id))
        if row is None:
            raise ApiError(ApiCode.NOT_FOUND, "运行不存在。", 404)
    await recover(run_id)
    async with session.read_session() as db:
        row = await db.scalar(owned_query(owner).where(AgentRun.id == run_id))
        if row is None:
            raise ApiError(ApiCode.NOT_FOUND, "运行不存在。", 404)
        return serialize(row)


async def list_runs(owner, params: PageParams, conversation_id=None, status=None):
    """分页查询本人运行，可按会话和状态筛选。"""
    statement = owned_query(owner)
    if conversation_id:
        statement = statement.where(AgentRun.conversation_id == conversation_id)
    if status:
        statement = statement.where(AgentRun.status == status)
    async with session.read_session() as db:
        rows, total = await paginate(db, statement.order_by(AgentRun.started_at.desc(), AgentRun.id.desc()), params)
        return {"item": [serialize(row) for row in rows], "page": params.page, "page_size": params.page_size, "total": total}


async def cancel(owner, run_id):
    """幂等取消本人的运行，跨 API 进程通知执行连接停止。"""
    record = await get(owner, run_id)
    async with session.transaction() as db:
        thread = await db.get(Conversation, record["conversation_id"], with_for_update=True)
        if thread is None or thread.owner_id != owner or thread.deleted_at is not None:
            raise ApiError(ApiCode.NOT_FOUND, "运行不存在。", 404)
        run = await db.get(AgentRun, run_id, with_for_update=True)
        if run.status == "running" and thread.run_token == run_id:
            await stop_locked(db, thread, "cancelled", "USER_CANCELLED", "用户已停止运行。")
        return serialize(run)


async def maintenance():
    """后台收敛异常退出后的运行，无需页面定时请求。"""
    while True:
        try:
            await recover()
        except Exception:
            log.warning("Agent 运行状态恢复失败，将稍后重试。")
        await asyncio.sleep(15)
