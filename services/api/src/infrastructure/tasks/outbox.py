"""事务消息投递、确认与中断恢复。"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from src.core import config
from src.infrastructure.database import session
from .models import TaskOutbox

KINDS = {'minutes', 'parse', 'vector', 'search'}


async def enqueue(db, kind, target_id, version):
    """在业务事务内写消息，相同业务版本只保留一条。"""
    if kind not in KINDS:
        raise ValueError('不支持的任务类型。')
    await db.execute(insert(TaskOutbox).values(id=str(uuid4()), kind=kind, target_id=target_id,
        version=str(version)).on_conflict_do_nothing(constraint='uq_task_outbox_target_version'))


async def claim():
    """并发投递器互斥领取，网络发送不占用事务。"""
    async with session.transaction() as db:
        row = await db.scalar(select(TaskOutbox).where(TaskOutbox.completed_at.is_(None),
            TaskOutbox.next_attempt_at <= func.now(),
            or_(TaskOutbox.lease_until.is_(None), TaskOutbox.lease_until < func.now()),
        ).order_by(TaskOutbox.next_attempt_at).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.claim_token = str(uuid4())
        row.lease_until = datetime.now(timezone.utc) + timedelta(seconds=30)
        row.attempts += 1
        await db.flush()
        return row


async def dispatched(message, error=False):
    """发送失败退避重试；已发送但未完成的消息定时补投。"""
    async with session.transaction() as db:
        row = await db.scalar(select(TaskOutbox).where(TaskOutbox.id == message.id,
            TaskOutbox.claim_token == message.claim_token, TaskOutbox.completed_at.is_(None)).with_for_update())
        if row is None:
            return
        row.claim_token = row.lease_until = None
        delay = min(60, 2 ** min(row.attempts, 6)) if error else config.MQ_REDELIVERY_SECONDS
        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        row.last_error = '消息队列暂不可用，恢复后自动投递。' if error else None
        if not error:
            row.published_at = func.now()


async def complete(message_id):
    """业务已完成或版本失效时停止补投，不覆盖业务结果。"""
    async with session.transaction() as db:
        await db.execute(update(TaskOutbox).where(TaskOutbox.id == message_id, TaskOutbox.completed_at.is_(None))
            .values(completed_at=func.now(), claim_token=None, lease_until=None, last_error=None))


async def defer(message_id, seconds=30):
    """未完成的消费稍后补投；不占用 Worker 等待租约或外部服务。"""
    async with session.transaction() as db:
        await db.execute(update(TaskOutbox).where(TaskOutbox.id == message_id, TaskOutbox.completed_at.is_(None)).values(
            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=seconds),
            published_at=func.coalesce(TaskOutbox.published_at, func.now()), claim_token=None, lease_until=None))
