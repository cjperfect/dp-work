"""验证语义召回、缓存及结构化记忆生命周期的一致性。"""
import asyncio
import json
from uuid import uuid4

from src.memory import repository as repo, vectors
from src.memory.schemas import MemoryWrite, MemoryUpdate, MemoryPreference
from src.memory.service import semantic_recall
from src.knowledge.rag.embedding import EmbeddingError


class Embeddings:
    def __init__(self):
        self.documents = []
        self.queries = []
        self.before_query = None

    async def aembed_documents(self, texts):
        self.documents.extend(texts)
        return [[1., 0.] if '异步' in text else [0., 1.] for text in texts]

    async def aembed_query(self, text):
        self.queries.append(text)
        if self.before_query:
            self.before_query()
        return [1., 0.]


def add(root, title, content, owner=1, **kwargs):
    return repo.save(owner, MemoryWrite(title=title, content=content, **kwargs), root=root)


def recall(root, embeddings, project=None, query='帮我实现并发请求', budget=5000):
    return asyncio.run(semantic_recall(1, 'general', project, query, budget, root, embeddings))


def test_semantic_match_not_keyword_and_reuse_persistent_index(tmp_path):
    chosen = add(tmp_path, '代码风格', '异步调用优先使用 async/await')
    add(tmp_path, '其他信息', '会议安排在周五')
    embeddings = Embeddings()
    result = recall(tmp_path, embeddings)
    assert [row['id'] for row in result['sources']] == [chosen['id']]
    assert len(embeddings.documents) == 2
    assert len(result['context']) <= 5000
    # 新实例从磁盘读取缓存，原正文仍保持在 memories 表。
    another = Embeddings()
    assert recall(tmp_path, another)['sources'] == result['sources']
    assert another.documents == []
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] == 2


def test_scope_precedence_and_user_isolation_before_embedding(tmp_path):
    project = str(uuid4())
    add(tmp_path, '代码风格', '异步用户级')
    add(tmp_path, '代码风格', '异步Agent级', scope='agent', agent_code='general')
    selected = add(tmp_path, '代码风格', '异步项目级', scope='project', project_id=project)
    add(tmp_path, '其他项目', '异步其他项目', scope='project', project_id=uuid4())
    add(tmp_path, '其他Agent', '异步其他Agent', scope='agent', agent_code='ui')
    add(tmp_path, '其他账号', '异步其他账号', owner=2)
    add(tmp_path, '已停用', '异步已停用', enabled=False)
    add(tmp_path, '已过期', '异步已过期', expires_at='2020-01-01T00:00:00Z')
    embeddings = Embeddings()
    result = recall(tmp_path, embeddings, project)
    assert [row['id'] for row in result['sources']] == [selected['id']]
    assert embeddings.documents == ['代码风格\n异步项目级']
    assert asyncio.run(semantic_recall(3, 'general', None, '查询', root=tmp_path, embeddings=embeddings))['sources'] == []
    assert not repo.memory_file(3, tmp_path).exists()


def test_edit_invalidates_index_delete_cascades_and_stale_cannot_return(tmp_path):
    row = add(tmp_path, '代码风格', '异步旧版本')
    recall(tmp_path, Embeddings())
    before = repo.relevant(1, 'general', None, tmp_path)
    repo.save(1, MemoryUpdate(title='代码风格', content='异步新版本', expected_revision=1), row['id'], tmp_path)
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 0
    vectors.store(1, before, [[1., 0.]], vectors.profile(), tmp_path)
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 0
    embed = Embeddings()
    assert '新版本' in recall(tmp_path, embed)['context']
    assert embed.documents == ['代码风格\n异步新版本']
    repo.remove(1, row['id'], 2, tmp_path)
    vectors.store(1, before, [[1., 0.]], vectors.profile(), tmp_path)
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 0


def test_model_profile_change_reindexes_and_corrupt_blob_repairs(tmp_path, monkeypatch):
    add(tmp_path, '代码风格', '异步请求')
    recall(tmp_path, Embeddings())
    monkeypatch.setattr(vectors, 'profile', lambda: 'new-model-space')
    embed = Embeddings()
    recall(tmp_path, embed)
    assert len(embed.documents) == 1
    with repo.connection(1, tmp_path, True) as db:
        db.execute("UPDATE memory_vectors SET vector=x'00'")
    repair = Embeddings()
    assert recall(tmp_path, repair)['sources']
    assert len(repair.documents) == 1


def test_provider_failure_falls_back_and_cancel_propagates(tmp_path):
    add(tmp_path, '代码风格', '异步偏好')
    class Broken(Embeddings):
        async def aembed_query(self, text):
            raise EmbeddingError('故障')
    assert '异步偏好' in recall(tmp_path, Broken())['context']
    async def check_cancel():
        class Waiting(Embeddings):
            async def aembed_query(self, text):
                await asyncio.Future()
        task = asyncio.create_task(semantic_recall(1, 'general', None, '问题', root=tmp_path, embeddings=Waiting()))
        await asyncio.sleep(.03)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError('取消必须向上传播')
    asyncio.run(check_cancel())


def test_changes_during_model_request_are_not_injected(tmp_path):
    row = add(tmp_path, '代码风格', '异步偏好')
    embeddings = Embeddings()
    embeddings.before_query = lambda: repo.remove(1, row['id'], 1, tmp_path)
    assert recall(tmp_path, embeddings)['sources'] == []
    add(tmp_path, '另一个偏好', '异步偏好')
    embeddings.before_query = lambda: repo.preferences(1, MemoryPreference(enabled=False, expected_revision=1), tmp_path)
    assert recall(tmp_path, embeddings)['sources'] == []


def test_empty_matches_budget_and_top_eight(tmp_path):
    add(tmp_path, '无关', '周五开会')
    assert recall(tmp_path, Embeddings())['sources'] == []
    for i in range(12):
        add(tmp_path, f'偏好{i}', '异步偏好' * 50)
    result = recall(tmp_path, Embeddings())
    assert len(result['sources']) == 8
    assert len(result['context']) <= 5000
    assert recall(tmp_path, Embeddings(), budget=50)['context'] == ''
    assert all('content' not in row for row in result['sources'])


def test_background_indexes_existing_memory_with_auto_generation_disabled(tmp_path, monkeypatch):
    from src import config
    from src.memory.worker import MemoryWorker
    from src.sessions.storage import SessionStorage
    monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'test-not-a-real-key')
    monkeypatch.setattr(config, 'MEMORY_AUTO_ENABLED', False)
    embeddings = Embeddings()
    monkeypatch.setattr(vectors, 'ArkEmbeddings', lambda: embeddings)
    add(tmp_path, '历史记忆', '异步约定')
    worker = MemoryWorker(SessionStorage(tmp_path))
    assert asyncio.run(worker.run_once()) == 0
    assert len(embeddings.documents) == 1
    assert asyncio.run(worker.run_once()) == 0
    assert len(embeddings.documents) == 1


def test_timeout_falls_back_without_losing_existing_index(tmp_path, monkeypatch):
    from src import config
    monkeypatch.setattr(config, 'MEMORY_RETRIEVAL_TIMEOUT_SECONDS', .01)
    add(tmp_path, '代码风格', '异步约定')
    class Waiting(Embeddings):
        async def aembed_query(self, text):
            await asyncio.Future()
    result = recall(tmp_path, Waiting())
    assert '异步约定' in result['context']
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 1
