"""任务组合层：MQ 消息映射到各业务执行器。"""
import asyncio
import logging
from sqlalchemy import select
from src.core import config
from src.infrastructure.sidecar.relay import DeviceOffline
from src.infrastructure.database import session
from src.infrastructure.tasks import outbox
from src.infrastructure.tasks.celery_app import celery_app
from src.infrastructure.tasks.models import TaskOutbox
from src.modules.meetings import generation
from src.modules.meetings.models import MeetingGenerationJob
from src.modules.knowledge import parsing, rag, search_index
from src.modules.knowledge.models import KnowledgeDocument
from src.modules.knowledge.search_models import KnowledgeSearchSync
from src.modules.knowledge.search_client import SearchClient

log = logging.getLogger(__name__)


async def is_finished(message):
    """过期版本、已删除对象与业务终态均停止补投。"""
    async with session.read_session() as db:
        if message.kind == 'minutes':
            row = await db.get(MeetingGenerationJob, message.target_id)
            return row is None or row.status not in ('queued', 'running')
        if message.kind == 'search':
            row = await db.get(KnowledgeSearchSync, message.target_id)
            return row is None or row.revision != int(message.version) or row.synced_revision >= int(message.version)
        row = await db.get(KnowledgeDocument, message.target_id)
        if row is None:
            return True
        if message.kind == 'parse':
            version = row.parse_started_at.isoformat() if row.parse_started_at else ''
            return version != message.version or row.parse_status not in ('queued', 'parsing')
        if message.kind == 'vector':
            return row.vector_task_id != message.version or row.vector_status not in ('queued', 'indexing')
        return True


async def execute(message_id, kind):
    """独立进程拥有自己的事件循环和连接池，执行结束后释放。"""
    await session.init_db()
    scope_token = None
    try:
        async with asyncio.timeout(config.MQ_TASK_TIME_LIMIT):
            async with session.read_session() as db:
                message = await db.get(TaskOutbox, message_id)
            if message is None or message.completed_at is not None or message.kind != kind:
                return
            if kind in ('minutes','parse','vector') and config.SIDECAR_TRANSPORT == 'device':
                from src.infrastructure.sidecar.context import scope
                from src.infrastructure.sidecar.relay import online_device
                from src.modules.meetings.models import Meeting
                from src.modules.knowledge.models import KnowledgeBase
                async with session.read_session() as db:
                    if kind == 'minutes':
                        owner = await db.scalar(select(Meeting.owner_id).join(MeetingGenerationJob,
                            MeetingGenerationJob.meeting_id == Meeting.id).where(MeetingGenerationJob.id == message.target_id))
                    else:
                        owner = await db.scalar(select(KnowledgeBase.owner_id).join(KnowledgeDocument,
                            KnowledgeDocument.knowledge_base_id == KnowledgeBase.id).where(KnowledgeDocument.id == message.target_id))
                scope_token = scope.set((owner, message.device_id))
                if owner is not None:
                    try: await online_device(owner, message.device_id)
                    except DeviceOffline:
                        await outbox.defer(message.id)
                        return
            if not await is_finished(message):
                if kind == 'minutes' and config.MINUTES_WORKER_ENABLED:
                    await generation.run_once(task_id=message.target_id)
                elif kind == 'parse' and config.DOCUMENT_PARSE_WORKER_ENABLED:
                    row = await parsing.claim(message.target_id, message.version)
                    if row: await parsing.process(row)
                elif kind == 'vector' and config.DOCUMENT_VECTOR_WORKER_ENABLED:
                    row = await rag.claim(message.target_id, message.version)
                    if row: await rag.process(row)
                elif kind == 'search' and config.ELASTICSEARCH_ENABLED:
                    client = SearchClient()
                    index_generation = await client.ensure_index()
                    row = await search_index.claim(message.target_id, message.version)
                    if row: await search_index.process(row, client, index_generation)
            if await is_finished(message):
                await outbox.complete(message.id)
            else:
                await outbox.defer(message.id)
    except DeviceOffline:
        if message is not None:
            await outbox.defer(message.id)
    finally:
        if scope_token is not None:
            from src.infrastructure.sidecar.context import scope
            scope.reset(scope_token)
        await session.close_db()


def consume(message_id, kind):
    """异常不含正文或凭证；未完成任务由 PG 消息表继续补投。"""
    try:
        asyncio.run(execute(message_id, kind))
    except Exception:
        # 不把数据库参数、上游响应等异常原文写入 Celery 日志。
        log.warning('任务执行中断，等待租约恢复，kind=%s, message=%s', kind, message_id)


@celery_app.task(name='dp_work.minutes')
def minutes(message_id):
    """生成会议纪要。"""
    consume(message_id, 'minutes')


@celery_app.task(name='dp_work.parse')
def parse(message_id):
    """解析文档。"""
    consume(message_id, 'parse')


@celery_app.task(name='dp_work.vector')
def vector(message_id):
    """生成文档向量。"""
    consume(message_id, 'vector')


@celery_app.task(name='dp_work.search')
def search(message_id):
    """同步 Elasticsearch 索引。"""
    consume(message_id, 'search')


async def recover_pending():
    """旧队列平滑迁移，以及过期任务和索引修订的持久化补偿。"""
    async with session.transaction() as db:
        jobs = (await db.execute(select(MeetingGenerationJob.id).where(
            MeetingGenerationJob.status.in_(['queued', 'running'])))).scalars().all()
        for key in jobs:
            await outbox.enqueue(db, 'minutes', key, key)
        documents = (await db.execute(select(KnowledgeDocument.id, KnowledgeDocument.parse_status,
            KnowledgeDocument.parse_started_at, KnowledgeDocument.vector_status, KnowledgeDocument.vector_task_id).where(
            (KnowledgeDocument.parse_status.in_(['queued', 'parsing'])) | (KnowledgeDocument.vector_status.in_(['queued', 'indexing']))))).all()
        for key, parse_status, parse_version, vector_status, vector_version in documents:
            if parse_status in ('queued', 'parsing') and parse_version:
                await outbox.enqueue(db, 'parse', key, parse_version.isoformat())
            if vector_status in ('queued', 'indexing') and vector_version:
                await outbox.enqueue(db, 'vector', key, vector_version)
        syncs = (await db.execute(select(KnowledgeSearchSync.document_id, KnowledgeSearchSync.revision).where(
            KnowledgeSearchSync.synced_revision < KnowledgeSearchSync.revision))).all()
        for key, version in syncs:
            await outbox.enqueue(db, 'search', key, version)
