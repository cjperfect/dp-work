"""本机单价、预算的校验、账号隔离和执行时生效。"""
import asyncio
from decimal import Decimal
import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src import config
from src.providers import local_settings
from src.usage import settings, ledger
from src.harness.usage import UsageLedger
from src.providers.llm.schemas import ModelError
from src.transport import handlers


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(config, 'ARK_MODEL', 'model')
    monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', '{"model":{"input":1,"output":4}}')
    monkeypatch.setattr(config, 'AGENT_COST_CURRENCY', 'CNY')
    monkeypatch.setattr(config, 'AGENT_RUN_TOKEN_LIMIT', 0)
    monkeypatch.setattr(config, 'AGENT_RUN_COST_LIMIT', '0')
    monkeypatch.setattr(config, 'ASR_PRICE_PER_HOUR', '')


def form(**changes):
    return dict(enabled=True, currency='USD', token_limit=100, cost_limit='0',
        model_prices={'model': {'input':'2', 'output':'8', 'cached_input':'1'}}, **changes)


def test_save_is_local_atomic_isolated_and_falls_back_when_disabled():
    local_settings.save(7, 'model', {'provider':'ark', 'enabled':True, 'base_url':'https://ark.cn-beijing.volces.com/api/v3', 'model':'model', 'api_key':'fixture-secret'})
    assert not settings.read(7)['enabled']
    saved = settings.save(7, form())
    assert saved['currency'] == 'USD' and saved['default']['currency'] == 'CNY'
    assert settings.effective(7)['token_limit'] == 100
    assert settings.effective(8)['token_limit'] == 0
    assert config.AGENT_RUN_TOKEN_LIMIT == 0
    assert local_settings.runtime(7, 'model').api_key.get_secret_value() == 'fixture-secret'
    assert local_settings.paths(7)[0].stat().st_mode & 0o777 == 0o600
    settings.save(7, {**form(), 'enabled':False})
    assert settings.effective(7)['currency'] == 'CNY'
    assert settings.read(7)['currency'] == 'USD'


@pytest.mark.parametrize('patch', [
    {'token_limit': -1}, {'token_limit': 1.5}, {'token_limit': True},
    {'cost_limit':'NaN'}, {'cost_limit':'Infinity'}, {'cost_limit':'-1'},
    {'currency':'usd'}, {'model_prices':{'': {'input':1,'output':2}}},
    {'model_prices':{'model': {'input':1,'output':-2}}},
    {'model_prices':{'model': {'input':1}}}, {'extra':1},
])
def test_invalid_config_does_not_overwrite(patch):
    settings.save(7, form())
    before = local_settings.paths(7)[0].read_bytes()
    with pytest.raises(ValueError):
        settings.save(7, {**form(), **patch})
    assert local_settings.paths(7)[0].read_bytes() == before


def test_cost_budget_requires_active_model_price():
    with pytest.raises(ValueError, match='当前模型'):
        settings.save(7, {**form(), 'cost_limit':'1', 'model_prices':{}})


def test_live_task_and_approval_resume_keep_budget_snapshot():
    settings.save(7, form())
    async def case():
        run = UsageLedger(str(uuid4()), 'model', 7)
        call = uuid4()
        await run.on_chat_model_start({}, [[]], run_id=call)
        result = LLMResult(generations=[[ChatGeneration(message=AIMessage('ok', usage_metadata={
            'input_tokens':100, 'output_tokens':20, 'total_tokens':120}))]])
        await run.on_llm_end(result, run_id=call)
        assert Decimal(run.snapshot()['estimated_cost']) == Decimal('0.00036')
        settings.save(7, {**form(), 'token_limit':0, 'currency':'CNY'})
        restored = UsageLedger(run.run_id, 'model', 7)
        assert restored.snapshot()['currency'] == 'USD' and restored.token_limit == 100
        for current in (run, restored):
            with pytest.raises(ModelError) as cause:
                await current.on_chat_model_start({}, [[]], run_id=uuid4())
            assert cause.value.code == 'AGENT_TOKEN_BUDGET'
        new = UsageLedger(str(uuid4()), 'model', 7)
        assert new.currency == 'CNY' and new.token_limit == 0
        other = UsageLedger(str(uuid4()), 'model', 8)
        assert other.prices['model']['input'] == '1'
    asyncio.run(case())


def test_summary_uses_account_prices_and_keeps_old_costs():
    settings.save(7, {**form(), 'asr_price_per_hour':'3.6'})
    value = {'input_tokens':1000000,'output_tokens':0,'total_tokens':1000000}
    ledger.write('old', 'model', value, owner=7, category='title')
    ledger.write('audio', 'asr', seconds=60, owner=7, category='asr')
    ledger.write('other', 'model', value, owner=8, category='title')
    settings.save(7, {**form(), 'model_prices':{'model':{'input':'9','output':'18'}}})
    rows = {row['category']:row for row in ledger.summary(7)['items']}
    assert rows['title']['currency'] == 'USD' and rows['title']['estimated_cost'] == '2'
    assert rows['asr']['estimated_cost'] == '0.06'
    assert ledger.summary(8)['items'][0]['estimated_cost'] == '1'


def test_rpc_uses_business_validation_and_does_not_expose_keys():
    async def case():
        saved = await handlers.dispatch('usage.settings.save', {'owner_id':7, 'body':form()}, None)
        assert saved['enabled']
        loaded = await handlers.dispatch('usage.settings.read', {'owner_id':7}, None)
        assert loaded == saved and 'api_key' not in json.dumps(loaded)
        with pytest.raises(handlers.OperationError) as cause:
            await handlers.dispatch('usage.settings.save', {'owner_id':7,'body':{**form(), 'token_limit':-1}}, None)
        assert cause.value.status == 400
    asyncio.run(case())


def test_cumulative_audio_keeps_price_at_start_and_new_calls_use_new_price():
    settings.save(7, {**form(), 'asr_price_per_hour':'3.6'})
    ledger.write('audio', 'asr', status='partial', seconds=30, owner=7, category='asr')
    settings.save(7, {**form(), 'currency':'CNY', 'asr_price_per_hour':'7.2'})
    ledger.write('audio', 'asr', seconds=60, owner=7, category='asr')
    ledger.write('next-audio', 'asr', seconds=60, owner=7, category='asr')
    rows = {row['currency']:row for row in ledger.summary(7)['items']}
    assert rows['USD']['estimated_cost'] == '0.06'
    assert rows['CNY']['estimated_cost'] == '0.12'
