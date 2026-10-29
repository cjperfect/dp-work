"""本机服务设置的隔离、加密、保留及执行器读取。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src import config
from src.providers import local_settings as settings
from src.transport import handlers


def model(**changes):
    return {'provider':'deepseek','enabled':True,'base_url':'https://api.deepseek.com',
            'model':'test-model','api_key':'private-fixture-key',**changes}


def test_storage_is_encrypted_isolated_atomic_and_masks_read(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    settings.save(7,'model',model())
    assert settings.runtime(7,'model').api_key.get_secret_value()=='private-fixture-key'
    assert settings.runtime(8,'model') is None
    assert settings.read(7)['model']['has_api_key']
    assert 'private-fixture-key' not in json.dumps(settings.read(7))
    assert 'private-fixture-key' not in settings.paths(7)[0].read_text()
    assert settings.paths(7)[0].stat().st_mode & 0o777 == 0o600
    keep=model(model='updated');keep.pop('api_key')
    settings.save(7,'model',keep)
    assert settings.runtime(7,'model').model=='updated'
    assert settings.runtime(7,'model').api_key.get_secret_value()=='private-fixture-key'
    switched={**keep,'provider':'openai','base_url':'https://api.openai.com/v1'}
    with pytest.raises(ValueError):settings.save(7,'model',switched)
    assert settings.runtime(7,'model').provider=='deepseek'
    assert settings.test_config(7,'model',{**keep,'model':'unsaved'}).model=='unsaved'
    assert settings.runtime(7,'model').model=='updated'
    with pytest.raises(ValueError):settings.save(7,'model',{**keep,'clear_api_key':True})
    settings.save(7,'model',{**keep,'enabled':False,'clear_api_key':True})
    assert settings.runtime(7,'model') is None
    assert not settings.read(7)['model']['has_api_key']


def test_asr_and_model_handlers_read_local_credentials(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    settings.save(7,'model',model())
    settings.save(7,'asr',{'provider':'doubao','enabled':True,
        'base_url':settings.defaults()['asr']['base_url'],'api_key':'local-asr-key'})
    async def case():
        models=await handlers.agent_models({'owner_id':7},None)
        assert models['models'][0]['id']=='test-model'
        state=SimpleNamespace(asr_tickets={})
        result=await handlers.asr_session({'owner_id':7,'meeting_id':'one'},state)
        assert state.asr_tickets[result['ticket']][3].api_key.get_secret_value()=='local-asr-key'
        assert 'local-asr-key' not in json.dumps(result)
        assert (await handlers.local_service_settings('read',{'owner_id':7},None))['model']['has_api_key']
        fake=AsyncMock(return_value={'ok':True})
        monkeypatch.setattr(handlers,'test_connection',fake)
        form=model();form.pop('api_key')
        assert (await handlers.local_service_settings('test-local',{'owner_id':7,'kind':'model','body':form},None))['ok']
        assert fake.call_args.args[1].api_key.get_secret_value()=='private-fixture-key'
    asyncio.run(case())


def test_connection_start_uses_local_model_without_returning_key(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    settings.save(7,'model',model())
    captured=[]
    async def fake_run(body,selected):
        captured.append(selected)
        yield {'type':'done','content':'ok'}
    monkeypatch.setattr(handlers,'run_agent',fake_run)
    async def case():
        stream=await handlers.agent_chat({'thread_id':'one','workspace_owner_id':7,
            'messages':[{'role':'user','content':'hi'}]},None)
        events=[e async for e in stream.events]
        assert events[-1]['content']=='ok'
        assert captured[0].api_key=='private-fixture-key'
        assert 'private-fixture-key' not in json.dumps(events)
    asyncio.run(case())
