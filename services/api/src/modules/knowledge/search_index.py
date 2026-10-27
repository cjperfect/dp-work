"""PG 持久化同步任务：异步重建 ES、删除补偿和租约恢复。"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from src.core import config
from src.infrastructure.database import session
from src.infrastructure.tasks.outbox import enqueue as enqueue_message
from .models import KnowledgeBase, KnowledgeDocument as Document
from .rag_models import KnowledgeParentChunk as Parent, KnowledgeChildChunk as Child
from .search_models import KnowledgeSearchSync as Sync
from .search_client import SearchClient, SearchError

log = logging.getLogger(__name__)


async def enqueue(db, document_id, task_id=None):
    """与正文修改或向量发布处于同一事务，覆盖旧同步请求。"""
    statement = insert(Sync).values(document_id=document_id, desired_task_id=task_id)
    revision = await db.scalar(statement.on_conflict_do_update(index_elements=[Sync.document_id], set_={
        "revision": Sync.revision + 1, "desired_task_id": task_id, "attempts": 0,
        "next_run_at": func.now(), "updated_at": func.now(), "claim_token": None, "lease_until": None, "last_error": None,
    }).returning(Sync.revision))
    await enqueue_message(db, "search", document_id, revision)


async def seed_existing(index_generation):
    """已有向量无需重算；ES 重建或索引名变更后从 PG 回填。"""
    async with session.transaction() as db:
        rows = (await db.execute(select(Document.id, Document.vector_task_id).outerjoin(Sync, Sync.document_id == Document.id).where(
            Document.vector_status == "indexed", Document.vectorized_at.is_not(None),
            or_(Sync.document_id.is_(None), Sync.desired_task_id.is_distinct_from(Document.vector_task_id),
                (Sync.index_generation.is_distinct_from(index_generation)) & (Sync.synced_revision == Sync.revision)),
        ).limit(100))).all()
        for document_id, task_id in rows:
            await enqueue(db, document_id, task_id)


async def claim(document_id=None, version=None):
    """多进程安全领取任务，过期租约可重领。"""
    async with session.transaction() as db:
        row = await db.scalar(select(Sync).where(Sync.synced_revision < Sync.revision,
            Sync.next_run_at <= func.now(), or_(Sync.lease_until.is_(None), Sync.lease_until < func.now()),
            *([Sync.document_id == document_id] if document_id is not None else []),
            *([Sync.revision == int(version)] if version is not None else []),
        ).order_by(Sync.next_run_at).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.claim_token = str(uuid4())
        row.lease_until = datetime.now(timezone.utc) + timedelta(seconds=180)
        row.attempts += 1
        await db.flush()
        return row


async def snapshot(document_id):
    """仅导出当前发布版本的文本子块，不读取向量。"""
    async with session.read_session() as db:
        rows = (await db.execute(select(Child.id, Child.content, Parent.id, Parent.chunk_metadata,
            Document.title, Document.knowledge_base_id, Document.vector_task_id, KnowledgeBase.owner_id).join(
            Parent, Parent.id == Child.parent_id).join(Document, Document.id == Parent.document_id).join(
            KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id).where(
            Document.id == document_id, Document.parse_status == "parsed", Document.vector_status == "indexed",
            Document.vectorized_at.is_not(None), Parent.task_id == Document.vector_task_id,
        ))).all()
        return [{"id": child_id, "content": content, "parent_id": parent_id,
            "headings": " / ".join(meta.get("headings", [])), "title": title,
            "knowledge_base_id": base_id, "document_id": document_id, "task_id": task_id, "owner_id": owner_id}
            for child_id, content, parent_id, meta, title, base_id, task_id, owner_id in rows]


async def finish(job, index_generation, error=None):
    """仅确认当前修订；旧请求若写入过 ES，强制再同步最新状态。"""
    async with session.transaction() as db:
        current = await db.scalar(select(Sync).where(Sync.document_id == job.document_id).with_for_update())
        if current is None:
            return
        if current.revision != job.revision or current.claim_token != job.claim_token:
            # 旧网络请求可能晚于新请求结束，不能把它造成的陈旧记录当作已同步。
            current.revision += 1
            current.next_run_at = func.now()
            if current.claim_token == job.claim_token:
                current.claim_token = current.lease_until = None
            return
        current.claim_token = current.lease_until = None
        if error:
            current.last_error = error[:300]
            current.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** min(current.attempts, 8)))
        else:
            current.synced_revision = current.revision
            current.index_generation = index_generation
            current.last_error = None
            document = await db.get(Document, job.document_id)
            if document and current.desired_task_id:
                from .parsing import notify_parse
                await db.flush()
                await notify_parse(db, document.knowledge_base_id, document.id)


async def process(job, client, index_generation):
    """网络写入期间不持有数据库事务。"""
    try:
        async with asyncio.timeout(120):
            await client.replace_document(job.document_id, await snapshot(job.document_id))
        await finish(job, index_generation)
    except asyncio.CancelledError:
        raise
    except (SearchError, TimeoutError, ValueError):
        await finish(job, index_generation, "关键词索引同步失败，服务恢复后会自动重试。")


async def maintenance():
    """只检查 ES 索引重建并提交回填消息，实际同步由 MQ 执行。"""
    if not config.ELASTICSEARCH_ENABLED:
        return
    generation = None
    last_check = 0
    while True:
        try:
            client = SearchClient()
            if generation is None or time.monotonic() - last_check > 30:
                generation = await client.ensure_index()
                await seed_existing(generation)
                last_check = time.monotonic()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception:
            generation = None
            log.warning("关键词索引服务暂不可用，30 秒后重试；语义检索仍可使用。")
            await asyncio.sleep(30)
