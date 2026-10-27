"""混合检索的权限、版本过滤和持久化同步恢复。"""
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import delete, select
from src.core import config
from src.infrastructure.database import session
from src.modules.knowledge import hybrid, search_index, service
from src.modules.knowledge.search_client import SearchClient, SearchError
from src.modules.knowledge.search_models import KnowledgeSearchSync as Sync
from src.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from src.modules.knowledge.rag_models import KnowledgeParentChunk as Parent, KnowledgeChildChunk as Child
from src.modules.users import service as users
from src.modules.users.models import User

PROFILE = 'a' * 64
VECTOR = [1.0] + [0.0] * 1023


def test_hybrid_scope_dedup_fallback_and_delete(monkeypatch):
    monkeypatch.setattr(config, 'ELASTICSEARCH_ENABLED', True)
    async def case():
        await session.init_db()
        owner = await users.create_user('hybrid-' + uuid4().hex, 'test', 'product')
        ids, children = [], []
        try:
            async with session.transaction() as db:
                for index in range(2):
                    base = KnowledgeBase(owner_id=owner.id, name='检索测试', description=''); db.add(base); await db.flush(); ids.append(base.id)
                    document = KnowledgeDocument(id='hybrid-' + uuid4().hex, knowledge_base_id=base.id, title='N6 mini', content='原文',
                        parse_status='parsed', parse_content='1800mAh', parsed_at=datetime.now(timezone.utc), vector_status='indexed',
                        vectorized_at=datetime.now(timezone.utc), vector_task_id=str(uuid4()), vector_profile=PROFILE)
                    db.add(document); await db.flush()
                    parent = Parent(id=str(uuid4()), document_id=document.id, task_id=document.vector_task_id, position=0,
                        content='N6 mini 电池容量为 1800mAh', chunk_metadata={'headings': ['电池']})
                    db.add(parent); await db.flush()
                    group = []
                    for position in range(2):
                        child = Child(id=str(uuid4()), parent_id=parent.id, position=position, content='1800mAh', start_offset=0, embedding=VECTOR)
                        db.add(child); group.append(child.id)
                    children.append(group)
                    if index == 0:
                        doc_id, task_id = document.id, document.vector_task_id
                    await search_index.enqueue(db, document.id, document.vector_task_id)
                    sync = await db.get(Sync, document.id); sync.synced_revision = sync.revision; sync.index_generation = 'fixture'
            # 模拟 ES 夹带其他知识库/不存在的子块；必须经 PG 过滤。
            mock = AsyncMock(return_value=[{'child_id': c, 'score': 100.0} for c in [children[1][0], 'missing', *children[0]]])
            monkeypatch.setattr(SearchClient, 'search', mock)
            result = await hybrid.search(owner.id, [ids[0]], 'N6mini 电池', VECTOR, PROFILE, 4)
            assert result['retrieval'] == {'mode': 'hybrid', 'keyword_pending': 0}
            assert len(result['sources']) == 1 and result['sources'][0]['document_id'] == doc_id
            assert result['sources'][0]['retrieval_channels'] == ['keyword', 'vector']
            assert '1800' in result['sources'][0]['content']
            assert mock.call_args.args[2] == [task_id]
            # 向量配置不匹配仍可按 BM25 获取当前发布版本。
            result = await hybrid.search(owner.id, [ids[0]], '电池', None, 'b' * 64, 4)
            assert result['retrieval']['mode'] == 'keyword' and len(result['sources']) == 1
            monkeypatch.setattr(SearchClient, 'search', AsyncMock(side_effect=SearchError('offline')))
            result = await hybrid.search(owner.id, [ids[0]], '电池', VECTOR, PROFILE, 4)
            assert result['retrieval']['mode'] == 'vector' and len(result['sources']) == 1
            assert '关键词服务暂不可用' in result['message']
            with pytest.raises(SearchError):
                await hybrid.search(owner.id, [ids[0]], '电池', None, PROFILE, 4)
            # 即使 ES 返回旧 ID，重新解析后也不可召回。
            monkeypatch.setattr(SearchClient, 'search', mock)
            async with session.transaction() as db:
                (await db.get(KnowledgeDocument, doc_id)).parse_status = 'unparsed'
            assert not (await hybrid.search(owner.id, [ids[0]], '电池', VECTOR, PROFILE, 4))['sources']
            await service.delete_document(owner.id, ids[0], doc_id)
            async with session.read_session() as db:
                tombstone = await db.get(Sync, doc_id)
                assert tombstone.desired_task_id is None and tombstone.revision > tombstone.synced_revision
            assert await search_index.snapshot(doc_id) == []
        finally:
            async with session.transaction() as db:
                documents = list((await db.scalars(select(KnowledgeDocument.id).where(KnowledgeDocument.knowledge_base_id.in_(ids)))).all())
                if 'doc_id' in locals(): documents.append(doc_id)
                await db.execute(delete(Sync).where(Sync.document_id.in_(documents)))
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(ids)))
                await db.execute(delete(User).where(User.id == owner.id))
            await session.close_db()
    asyncio.run(case())


def test_sync_retry_expired_lease_and_stale_writer(monkeypatch):
    async def case():
        await session.init_db()
        key = 'sync-' + uuid4().hex
        try:
            # 删除墓碑无需对应文档，任务与事务一起提交。
            async with session.transaction() as db:
                await search_index.enqueue(db, key)
            # 独立测试任务优先领取，不清理其它测试记录。
            async def take():
                async with session.transaction() as db:
                    (await db.get(Sync, key)).next_run_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
                return await search_index.claim()
            abandoned = await take()
            async with session.transaction() as db:
                (await db.get(Sync, key)).lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            newer = await take()
            assert newer.claim_token != abandoned.claim_token
            await search_index.finish(abandoned, 'generation')
            async with session.read_session() as db:
                row = await db.get(Sync, key)
                assert row.claim_token == newer.claim_token and row.revision > newer.revision
            await search_index.finish(newer, 'generation')
            job = await take()
            failing = AsyncMock(); failing.replace_document.side_effect = SearchError('failure')
            await search_index.process(job, failing, 'generation')
            async with session.transaction() as db:
                row = await db.get(Sync, key)
                assert row.last_error and row.synced_revision < row.revision
                assert row.claim_token is None and row.next_run_at > datetime.now(timezone.utc)
                row.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            client = AsyncMock()
            await search_index.process(await take(), client, 'generation')
            client.replace_document.assert_awaited_once_with(key, [])
            async with session.read_session() as db:
                row = await db.get(Sync, key)
                assert row.synced_revision == row.revision and row.index_generation == 'generation' and row.last_error is None
        finally:
            async with session.transaction() as db:
                await db.execute(delete(Sync).where(Sync.document_id == key))
            await session.close_db()
    asyncio.run(case())


def test_existing_vectors_backfill_and_new_index_generation(monkeypatch):
    async def case():
        await session.init_db()
        owner = await users.create_user('backfill-' + uuid4().hex, 'test', 'product')
        base_id = None; key = 'backfill-' + uuid4().hex
        try:
            async with session.transaction() as db:
                base = KnowledgeBase(owner_id=owner.id, name='回填', description=''); db.add(base); await db.flush(); base_id = base.id
                db.add(KnowledgeDocument(id=key, knowledge_base_id=base_id, title='回填', content='', parse_status='parsed',
                    vector_status='indexed', vectorized_at=datetime.now(timezone.utc), vector_task_id=str(uuid4())))
            await search_index.seed_existing('old-generation')
            async with session.transaction() as db:
                row = await db.get(Sync, key)
                assert row and row.desired_task_id is not None
                row.synced_revision = row.revision; row.index_generation = 'old-generation'
                revision = row.revision
            await search_index.seed_existing('old-generation')
            async with session.read_session() as db:
                assert (await db.get(Sync, key)).revision == revision
            await search_index.seed_existing('new-generation')
            async with session.read_session() as db:
                row = await db.get(Sync, key)
                assert row.revision == revision + 1 and row.synced_revision == revision
        finally:
            async with session.transaction() as db:
                await db.execute(delete(Sync).where(Sync.document_id == key))
                if base_id: await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == base_id))
                await db.execute(delete(User).where(User.id == owner.id))
            await session.close_db()
    asyncio.run(case())
