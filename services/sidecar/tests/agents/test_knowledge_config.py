"""知识库关联的 SQLite 持久化、账号隔离及迁移幂等。"""
import asyncio
import sqlite3

import pytest
from pydantic import ValidationError

from src import config
from src.agents.knowledge import operation
from src.transport.handlers import dispatch, OperationError


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)


def test_write_reopen_and_account_agent_isolation(tmp_path):
    assert operation('save', 1, {'agent_code': 'general', 'knowledge_base_ids': [13, 13, 1]}) == {'general': [13, 1]}
    operation('save', 1, {'agent_code': 'ui', 'knowledge_base_ids': [2]})
    assert operation('read', 2, {}) == {}
    assert operation('read', 1, {}) == {'general': [13, 1], 'ui': [2]}
    with sqlite3.connect(tmp_path / 'data/users/1/state.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM agent_knowledge_config').fetchone()[0] == 2


def test_migration_never_overwrites_saved_empty_selection():
    body = {'agents': [{'agent_code': 'general', 'knowledge_base_ids': [13]}]}
    assert operation('import', 1, body) == {'general': [13]}
    operation('save', 1, {'agent_code': 'general', 'knowledge_base_ids': []})
    assert operation('import', 1, body) == {'general': []}
    assert operation('import', 2, body) == {'general': [13]}


@pytest.mark.parametrize('ids', [[True], [0], [-1], ['server-13'], [1] * 21])
def test_invalid_ids_cannot_replace_existing_state(ids):
    operation('save', 1, {'agent_code': 'general', 'knowledge_base_ids': [13]})
    with pytest.raises(ValidationError):
        operation('save', 1, {'agent_code': 'general', 'knowledge_base_ids': ids})
    assert operation('read', 1, {}) == {'general': [13]}


def test_rpc_dispatch_and_safe_storage_error(monkeypatch):
    async def case():
        assert await dispatch('agents.knowledge.save', {'owner_id': 1, 'body': {
            'agent_code': 'general', 'knowledge_base_ids': [13]}}, None) == {'general': [13]}
        from src.agents import knowledge
        def failed(*args):
            raise sqlite3.OperationalError('private filesystem detail')
        monkeypatch.setattr(knowledge, 'operation', failed)
        with pytest.raises(OperationError) as error:
            await dispatch('agents.knowledge.read', {'owner_id': 1}, None)
        assert error.value.status == 500
        assert 'private filesystem' not in str(error.value)
    asyncio.run(case())
