import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from src import config
from src.usage import ledger


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', json.dumps({'model':{'input':1,'output':2}}))
    monkeypatch.setattr(config, 'ASR_PRICE_PER_HOUR', '3.6')


def test_isolation_dedup_unknown_cost_and_usage():
    with ledger.scope(1, 'agent', 'task'):
        ledger.write('call', 'model', {'input_tokens':100, 'output_tokens':50, 'total_tokens':150})
        ledger.write('call', 'model', {'input_tokens':200, 'output_tokens':50, 'total_tokens':250})
        ledger.write('unknown', 'model', status='unreported')
        ledger.write('audio', 'asr', seconds=60, category='asr')
    rows = {row['category']:row for row in ledger.summary(1)['items']}
    assert rows['agent']['calls'] == 2
    assert rows['agent']['total_tokens'] == 250
    assert rows['agent']['unpriced_calls'] == 1
    assert rows['agent']['estimated_cost'] == '0.0003'
    assert rows['asr']['audio_seconds'] == 60
    assert rows['asr']['estimated_cost'] == '0.06'
    assert ledger.summary(2)['items'] == []
    with pytest.raises(ValueError): ledger.summary('../1')


def test_reported_tokens_only_and_unpriced_embedding():
    assert ledger.raw_usage({'usage':{'total_tokens':10}}) == {'total_tokens':10}
    assert ledger.raw_usage({}) is None
    with ledger.scope(1, 'embedding'):
        ledger.write('embed', 'no-price', {'total_tokens':10})
    assert ledger.summary(1)['items'][0]['estimated_cost'] is None


def test_cancelled_raw_call_is_unknown_and_scope_restored():
    @ledger.tracked
    async def call(messages, settings):
        raise asyncio.CancelledError()
    async def case():
        with ledger.scope(1, 'memory'):
            with pytest.raises(asyncio.CancelledError):
                await call([], SimpleNamespace(model='model'))
        assert ledger.context.get()[0] is None
        assert ledger.current_call.get() is None
    asyncio.run(case())
    row=ledger.summary(1)['items'][0]
    assert row['category'] == 'memory' and row['unreported_calls'] == 1


def test_asr_saves_actual_sent_audio_and_close_is_idempotent():
    from src.meetings.session import AsrSession
    provider=SimpleNamespace(send_audio=AsyncMock(), close=AsyncMock())
    async def case():
        session=AsrSession('meeting', AsyncMock(), provider, owner_id=1)
        await session.send_audio(b'\0' * 32000)
        await session.close()
        await session.close()
    asyncio.run(case())
    row=ledger.summary(1)['items'][0]
    assert row['calls'] == 1 and row['audio_seconds'] == 1


def test_price_snapshot_is_not_changed_by_later_configuration(monkeypatch):
    with ledger.scope(1,'title'):
        ledger.write('title-call','model',{'input_tokens':1000000,'output_tokens':0,'total_tokens':1000000})
    monkeypatch.setattr(config,'AGENT_MODEL_PRICES','{}')
    assert ledger.summary(1)['items'][0]['estimated_cost']=='1'


def test_raw_client_records_provider_usage_without_payload():
    import httpx
    from src.providers.llm.client import complete
    from src.providers.llm.schemas import ModelSettings
    async def case():
        with ledger.scope(1,'memory'):
            await complete([{'role':'user','content':'PRIVATE INPUT'}], ModelSettings(api_key='test',model='model',base_url='https://model.test'), httpx.MockTransport(lambda request: httpx.Response(200,json={'model':'model','choices':[{'finish_reason':'stop','message':{'content':'ok'}}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})))
    asyncio.run(case())
    row=ledger.summary(1)['items'][0]
    assert row['category']=='memory' and row['total_tokens']==15
    db=ledger.database(1)
    try: assert 'PRIVATE INPUT' not in str(db.execute('SELECT * FROM usage_events').fetchall())
    finally: db.close()


def test_dispatch_stream_preserves_verified_usage_scope(monkeypatch):
    from src.transport import handlers
    async def fake(params,state):
        assert '_usage_owner_id' not in params
        async def events():
            ledger.write('stream-call','model',{'input_tokens':1,'output_tokens':1,'total_tokens':2})
            yield {'type':'done'}
        return handlers.EventStream(events())
    monkeypatch.setitem(handlers.HANDLERS,'agents.chat',fake)
    async def case():
        stream=await handlers.dispatch('agents.chat',{'_usage_owner_id':7},None)
        assert ledger.context.get()[0] is None
        assert [row async for row in stream.events] == [{'type':'done'}]
        assert ledger.context.get()[0] is None
    asyncio.run(case())
    assert ledger.summary(7)['items'][0]['total_tokens']==2
    assert ledger.summary(1)['items']==[]
