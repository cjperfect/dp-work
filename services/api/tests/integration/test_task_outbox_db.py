"""事务消息、重复投递、租约恢复和业务终态通知。"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import delete, func, select
from src.infrastructure.database import session
from src.infrastructure.tasks import outbox
from src.infrastructure.tasks.models import TaskOutbox
from src.task_dispatcher import dispatch_once
from src.task_handlers import execute
from src.modules.knowledge import service, parsing
from src.modules.knowledge.schemas import KnowledgeBaseCreate, KnowledgeDocumentSave
from src.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from src.modules.knowledge.search_models import KnowledgeSearchSync
from src.modules.users import service as users
from src.modules.users.models import User


def test_outbox_atomicity_publish_retry_and_completion_race():
    async def case():
        await session.init_db()
        target = 'outbox-' + uuid4().hex
        try:
            with pytest.raises(RuntimeError):
                async with session.transaction() as db:
                    await outbox.enqueue(db, 'parse', target, 'rollback')
                    raise RuntimeError('rollback')
            async with session.read_session() as db:
                assert not await db.scalar(select(func.count()).select_from(TaskOutbox).where(TaskOutbox.target_id == target))
            async with session.transaction() as db:
                await outbox.enqueue(db, 'search', target, 1)
                await outbox.enqueue(db, 'search', target, 1)
                row = await db.scalar(select(TaskOutbox).where(TaskOutbox.target_id == target))
                message_id = row.id
                row.next_attempt_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            def unavailable(_):
                raise RuntimeError('secret broker response')
            assert await dispatch_once(unavailable)
            async with session.transaction() as db:
                row = await db.get(TaskOutbox, message_id)
                assert row.attempts == 1 and row.published_at is None and row.last_error
                assert 'secret' not in row.last_error and row.next_attempt_at > datetime.now(timezone.utc)
                row.next_attempt_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            abandoned = await outbox.claim()
            async with session.transaction() as db:
                row = await db.get(TaskOutbox, message_id)
                row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
                row.next_attempt_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            recovered = await outbox.claim()
            assert recovered.id == message_id and recovered.claim_token != abandoned.claim_token
            await outbox.dispatched(abandoned)
            async with session.read_session() as db:
                assert (await db.get(TaskOutbox, message_id)).published_at is None
            await outbox.dispatched(recovered)
            async with session.read_session() as db:
                assert (await db.get(TaskOutbox, message_id)).published_at
            await outbox.complete(message_id)
            await outbox.dispatched(recovered, error=True)
            await outbox.defer(message_id)
            async with session.read_session() as db:
                row = await db.get(TaskOutbox, message_id)
                assert row.completed_at and row.last_error is None
        finally:
            async with session.transaction() as db:
                await db.execute(delete(TaskOutbox).where(TaskOutbox.target_id == target))
            await session.close_db()
    asyncio.run(case())


def test_consumer_executes_only_target_and_skips_duplicate_or_deleted_document(monkeypatch):
    upstream = AsyncMock(return_value={'status': 'parsed', 'content': '完成的解析结果', 'metadata': []})
    monkeypatch.setattr(parsing, 'sidecar', upstream)
    async def case():
        await session.init_db()
        owner = await users.create_user('mq-consumer-' + uuid4().hex, 'fixture', 'product')
        base = await service.create_knowledge_base(owner.id, KnowledgeBaseCreate(name='消费者测试'))
        keys = ['mq-' + uuid4().hex for _ in range(2)]
        try:
            for key in keys:
                await service.save_document(owner.id, base.id, key, KnowledgeDocumentSave(content='文档正文'))
                await parsing.request_parse(owner.id, base.id, key)
            async with session.read_session() as db:
                message = await db.scalar(select(TaskOutbox).where(TaskOutbox.kind == 'parse', TaskOutbox.target_id == keys[1]))
                message_id = message.id
            await execute(message_id, 'parse')
            await session.init_db()
            async with session.read_session() as db:
                assert (await db.get(KnowledgeDocument, keys[1])).parse_status == 'parsed'
                assert (await db.get(KnowledgeDocument, keys[0])).parse_status == 'queued'
                assert (await db.get(TaskOutbox, message_id)).completed_at
            await execute(message_id, 'parse')
            upstream.assert_awaited_once()
            await session.init_db()
            async with session.read_session() as db:
                other = await db.scalar(select(TaskOutbox).where(TaskOutbox.kind == 'parse', TaskOutbox.target_id == keys[0]))
                other_id = other.id
            await service.delete_document(owner.id, base.id, keys[0])
            await execute(other_id, 'parse')
            upstream.assert_awaited_once()
            await session.init_db()
            async with session.read_session() as db:
                assert (await db.get(TaskOutbox, other_id)).completed_at
        finally:
            await session.init_db()
            async with session.transaction() as db:
                await db.execute(delete(TaskOutbox).where(TaskOutbox.target_id.in_(keys)))
                await db.execute(delete(KnowledgeSearchSync).where(KnowledgeSearchSync.document_id.in_(keys)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == base.id))
                await db.execute(delete(User).where(User.id == owner.id))
            await session.close_db()
    asyncio.run(case())
