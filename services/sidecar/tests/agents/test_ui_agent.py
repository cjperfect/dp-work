"""UI 伙伴拥有独立提示词与稳定会话归属。"""
import asyncio
from unittest.mock import AsyncMock
from src import config
from src.agents.context import read_prompt
from src.transport.handlers import AgentInput
from src.sessions import service
from src.sessions.storage import SessionStorage


def test_ui_template_and_workspace_are_independent(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    prompt=read_prompt('ui')
    assert '# UI Agent' in prompt
    assert (tmp_path/'workspace/ui/AGENT.md').is_file()
    assert not (tmp_path/'workspace/product').exists()
    body=AgentInput(agent_code='ui',thread_id='ui-thread',messages=[{'role':'user','content':'设计页面'}])
    assert body.agent_code=='ui'


def test_ui_conversation_round_trip_uses_agent_id_three(monkeypatch,tmp_path):
    store=SessionStorage(tmp_path)
    monkeypatch.setattr(service,'storage',store)
    async def case():
        created=await service.operation('create',{'owner_id':7,'body':{'id':'ui-thread','agent_id':3}})
        assert created['thread']['agent_id']==3
        detail=await service.operation('get',{'owner_id':7,'thread_id':'ui-thread'})
        assert detail['thread']['agent_id']==3
    asyncio.run(case())
