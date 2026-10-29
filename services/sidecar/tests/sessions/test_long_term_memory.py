"""长期记忆只保存精选事实，按账号和当前范围加载。"""
import json
from uuid import uuid4
import pytest
from pydantic import ValidationError
from src.memory import repository as repo
from src.memory.schemas import MemoryWrite, MemoryUpdate, MemoryQuery, MemoryPreference
from src.memory.service import recall


def add(root, title='语言偏好', content='优先使用中文', **kwargs):
    return repo.save(1, MemoryWrite(title=title, content=content, **kwargs), root=root)


def test_memory_crud_cas_and_forget(tmp_path):
    row = add(tmp_path)
    assert repo.memory_file(1, tmp_path) == tmp_path / 'memories/1/memory.sqlite3'
    assert repo.list_memories(1, MemoryQuery(), tmp_path)['item'][0]['content'] == '优先使用中文'
    assert repo.list_memories(2, MemoryQuery(), tmp_path)['total'] == 0
    with pytest.raises(repo.MemoryError, match='同名'):
        add(tmp_path, title='  语言偏好  ')
    data = MemoryUpdate(title='语言偏好', content='回答保持简洁', expected_revision=1)
    updated = repo.save(1, data, row['id'], tmp_path)
    assert updated['revision'] == 2
    with pytest.raises(repo.MemoryError, match='其他窗口'):
        repo.save(1, data, row['id'], tmp_path)
    with pytest.raises(repo.MemoryError, match='修改'):
        repo.remove(1, row['id'], 1, tmp_path)
    repo.remove(1, row['id'], 2, tmp_path)
    assert recall(1, 'general', None, root=tmp_path)['sources'] == []
    with repo.connection(1, tmp_path) as db:
        assert db.execute('SELECT COUNT(*) FROM memory_revisions').fetchone()[0] == 0
        assert set(dict(db.execute('SELECT * FROM memory_tombstones').fetchone())) == {'id', 'revision', 'deleted_at'}
    with pytest.raises(repo.MemoryError, match='已删除'):
        repo.save(1, data, row['id'], tmp_path)


def test_scope_priority_expiry_and_switch(tmp_path):
    project = str(uuid4())
    add(tmp_path, content='用户默认')
    add(tmp_path, content='Agent 优先', scope='agent', agent_code='general')
    chosen = add(tmp_path, content='当前项目优先', scope='project', project_id=project)
    add(tmp_path, title='其他Agent', scope='agent', agent_code='ui')
    add(tmp_path, title='其他项目', scope='project', project_id=uuid4())
    add(tmp_path, title='已停用', enabled=False)
    add(tmp_path, title='已过期', expires_at='2020-01-01T00:00:00Z')
    result = recall(1, 'general', project, root=tmp_path)
    assert [row['content'] for row in json.loads(result['context'])] == ['当前项目优先']
    assert result['sources'][0]['id'] == chosen['id']
    assert 'content' not in result['sources'][0]
    assert json.loads(recall(1, 'product', None, root=tmp_path)['context'])[0]['content'] == '用户默认'
    repo.preferences(1, MemoryPreference(enabled=False, expected_revision=1), tmp_path)
    assert recall(1, 'general', project, root=tmp_path)['context'] == ''
    with pytest.raises(repo.MemoryError, match='其他窗口'):
        repo.preferences(1, MemoryPreference(enabled=True, expected_revision=1), tmp_path)


def test_recall_bounded_and_read_only(tmp_path):
    assert recall(1, 'general', None, root=tmp_path)['sources'] == []
    assert not repo.memory_file(1, tmp_path).exists()
    for i in range(12):
        add(tmp_path, title=f'关键约定{i}', content='精选信息' * 100)
    before = repo.list_memories(1, MemoryQuery(), tmp_path)['total']
    for _ in range(3):
        result = recall(1, 'general', None, root=tmp_path)
        assert len(result['sources']) <= 8
        assert len(result['context']) <= 5000
        assert recall(2, 'general', None, root=tmp_path)['sources'] == []
    assert repo.list_memories(1, MemoryQuery(), tmp_path)['total'] == before
    assert recall(1, 'general', None, budget=50, root=tmp_path)['context'] == ''


@pytest.mark.parametrize('data', [dict(title=' ',content='x'),dict(title='x',content='x',scope='agent'),dict(title='x',content='x',scope='user',agent_code='ui'),dict(title='x',content='x',owner_id=2)])
def test_memory_validation(data):
    with pytest.raises(ValidationError):
        MemoryWrite.model_validate(data)


def test_search_escapes_wildcards(tmp_path):
    add(tmp_path,title='100%准确')
    add(tmp_path,title='100条约定')
    result = repo.list_memories(1, MemoryQuery(q='%', page_size=1), tmp_path)
    assert result['total'] == 1
    assert result['item'][0]['title'] == '100%准确'
