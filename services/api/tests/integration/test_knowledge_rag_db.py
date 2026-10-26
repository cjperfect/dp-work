"""pgvector 父子召回、权限、版本失效与任务恢复。"""
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import delete, select, func
from httpx import ASGITransport, AsyncClient
from app.core.exceptions import ApiError
from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge import rag, rag_access, parsing
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from app.modules.knowledge.rag_models import KnowledgeParentChunk as Parent, KnowledgeChildChunk as Child
from app.modules.knowledge.schemas import ParsedDocumentSave
from app.modules.users import service as users
from app.modules.users.models import User

PROFILE = 'a' * 64
VECTOR = [1.0] + [0.0] * 1023


def test_vector_pipeline_is_atomic_scoped_and_invalidated_on_edit(monkeypatch):
    async def upstream(path, data):
        if path == 'chunks':
            return {'parents': [{'content': '父块包含完整规定：审批人是林悦。', 'metadata': {'headings': ['规定']}, 'children': [
                {'content': '审批人是林悦', 'start': 0}, {'content': '完整规定', 'start': 9}]}]}
        return {'vectors': [VECTOR for text in data['texts']], 'dimensions': 1024, 'model': 'fixture', 'profile': PROFILE}
    monkeypatch.setattr(rag, 'call_sidecar', upstream)
    async def case():
        await session.init_db()
        owners, base_ids = [], []
        try:
            for index in range(2):
                owner = await users.create_user('rag-' + uuid4().hex, 'test', 'product')
                owners.append(owner)
                async with session.transaction() as db:
                    base = KnowledgeBase(owner_id=owner.id, name='知识库' + str(index), description='')
                    db.add(base); await db.flush(); base_ids.append(base.id)
                    document = KnowledgeDocument(id='rag-' + uuid4().hex, knowledge_base_id=base.id, title='规定', content='原文',
                        parse_status='parsed', parse_content='审批人是林悦', parsed_at=datetime.now(timezone.utc))
                    db.add(document); await db.flush()
                    if index == 0:
                        document_id, parsed_at = document.id, document.parsed_at
            owner, other = owners
            before = await rag_access.retrieve_with_status(rag_access.issue_capability(owner.id, [base_ids[0]]), VECTOR, PROFILE, 4)
            assert before['coverage']['ready'] == 0 and before['sources'] == []
            assert '向量化' in before['message']
            # 未授权知识库不能提交；版本不匹配不能提交。
            with pytest.raises(ApiError):
                await rag.enqueue(other.id, base_ids[0], document_id, parsed_at)
            with pytest.raises(ApiError):
                await rag.enqueue(owner.id, base_ids[0], document_id, parsed_at - timedelta(seconds=1))
            result = await rag.enqueue(owner.id, base_ids[0], document_id, parsed_at)
            again = await rag.enqueue(owner.id, base_ids[0], document_id, parsed_at)
            assert result.vector_task_id == again.vector_task_id
            job = await rag.claim()
            await rag.process(job)
            async with session.read_session() as db:
                document = await db.get(KnowledgeDocument, document_id)
                assert document.vector_status == 'indexed' and document.vector_done == document.vector_total == 2
                assert document.vectorized_at and document.vector_profile == PROFILE
                assert await db.scalar(select(func.count()).select_from(Child).join(Parent).where(Parent.document_id == document_id)) == 2
            sources = await rag.search_vector(owner.id, [base_ids[0]], VECTOR, PROFILE)
            assert len(sources) == 1 and '完整规定' in sources[0]['content']
            assert (await rag_access.retrieve_with_status(rag_access.issue_capability(owner.id, [base_ids[0]]), VECTOR, PROFILE, 4))['coverage']['ready'] == 1
            assert sources[0]['document_id'] == document_id
            assert not await rag.search_vector(other.id, [base_ids[1]], VECTOR, PROFILE)
            assert not await rag.search_vector(owner.id, [base_ids[0]], VECTOR, 'b' * 64)
            with pytest.raises(ApiError):
                await rag.search_vector(other.id, [base_ids[0]], VECTOR, PROFILE)
            # 能力令牌不能扩大知识库范围；普通登录令牌不能挪作能力令牌。
            capability = rag_access.issue_capability(owner.id, [base_ids[0]])
            assert len(await rag_access.retrieve(capability, VECTOR, PROFILE, 4)) == 1
            with pytest.raises(ApiError):
                await rag_access.retrieve(create_access_token(owner.id, owner.role, owner.department), VECTOR, PROFILE, 4)
            # 编辑解析结果后旧向量即刻不可召回。
            edited = await parsing.save_parsed(owner.id, base_ids[0], document_id,
                ParsedDocumentSave(content='修改后的新规定', blocks=None, expected_parsed_at=parsed_at))
            assert edited.vector_status == 'unindexed' and edited.vectorized_at is None
            assert not await rag.search_vector(owner.id, [base_ids[0]], VECTOR, PROFILE)
            # 执行期间再次编辑，旧任务完成也不得回写。
            await rag.enqueue(owner.id, base_ids[0], document_id, edited.parsed_at)
            job = await rag.claim()
            await parsing.save_parsed(owner.id, base_ids[0], document_id,
                ParsedDocumentSave(content='更新的正文', blocks=None, expected_parsed_at=edited.parsed_at))
            await rag.process(job)
            async with session.read_session() as db:
                assert (await db.get(KnowledgeDocument, document_id)).vectorized_at is None
            # 用户搜索接口也会检查知识库权限。
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test') as client:
                headers = {'Authorization': 'Bearer ' + create_access_token(other.id, other.role, other.department)}
                response = await client.post('/api/knowledge-bases/search', headers=headers, json={'knowledge_base_ids': [base_ids[0]], 'query': '审批人是谁？'})
                assert response.status_code == 404
        finally:
            async with session.transaction() as db:
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(base_ids)))
                await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())


def test_partial_vectors_are_hidden_and_expired_claims_cannot_publish(monkeypatch):
    mode = {'fail': True}
    async def upstream(path, data):
        if path == 'chunks':
            return {'parents': [{'content': '完整父块', 'metadata': {}, 'children': [{'content': f'子块{i}', 'start': i} for i in range(18)]}]}
        if data['texts'][0] == '子块16' and mode['fail']:
            raise ValueError('模拟第二批失败')
        return {'vectors': [VECTOR for _ in data['texts']], 'dimensions': 1024, 'profile': PROFILE}
    monkeypatch.setattr(rag, 'call_sidecar', upstream)
    async def case():
        await session.init_db()
        owner = None; base_id = None
        try:
            owner = await users.create_user('rag-retry-' + uuid4().hex, 'test', 'product')
            async with session.transaction() as db:
                base = KnowledgeBase(owner_id=owner.id, name='重试测试', description=''); db.add(base); await db.flush(); base_id = base.id
                document = KnowledgeDocument(id='rag-' + uuid4().hex, knowledge_base_id=base.id, title='重试文档', content='正文',
                    parse_status='parsed', parse_content='正文', parsed_at=datetime.now(timezone.utc))
                db.add(document); await db.flush(); document_id, parsed_at = document.id, document.parsed_at
            await rag.enqueue(owner.id, base_id, document_id, parsed_at)
            await rag.process(await rag.claim())
            async with session.read_session() as db:
                row = await db.get(KnowledgeDocument, document_id)
                assert row.vector_status == 'failed' and row.vector_done == 16 and row.vectorized_at is None
            assert not await rag.search_vector(owner.id, [base_id], VECTOR, PROFILE)
            mode['fail'] = False
            await rag.enqueue(owner.id, base_id, document_id, parsed_at)
            abandoned = await rag.claim()
            async with session.transaction() as db:
                (await db.get(KnowledgeDocument, document_id)).vector_lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            recovered = await rag.claim()
            assert recovered.vector_claim_token != abandoned.vector_claim_token
            await rag.process(abandoned)
            async with session.read_session() as db:
                assert (await db.get(KnowledgeDocument, document_id)).vector_status == 'indexing'
            await rag.process(recovered)
            async with session.read_session() as db:
                row = await db.get(KnowledgeDocument, document_id)
                assert row.vector_status == 'indexed' and row.vector_done == 18
                assert await db.scalar(select(func.count()).select_from(Child).join(Parent).where(Parent.document_id == document_id)) == 18
            assert len(await rag.search_vector(owner.id, [base_id], VECTOR, PROFILE)) == 1
            async with session.transaction() as db:
                await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
            async with session.read_session() as db:
                assert not await db.scalar(select(func.count()).select_from(Parent).where(Parent.document_id == document_id))
        finally:
            async with session.transaction() as db:
                if base_id: await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == base_id))
                if owner: await db.execute(delete(User).where(User.id == owner.id))
            await session.close_db()
    asyncio.run(case())
