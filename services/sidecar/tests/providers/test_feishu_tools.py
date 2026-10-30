import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from src.connectors import cli, service
from src.connectors.tools import business_tools
from src.harness.approvals import GATED_TOOLS


def test_unconnected_account_gets_no_tools(monkeypatch):
    monkeypatch.setattr(cli,'binary',lambda:None)
    assert business_tools(1)==[] and business_tools(None)==[]


def test_tools_use_verified_owner_fixed_commands_and_temp_content(monkeypatch,tmp_path):
    monkeypatch.setattr(cli,'binary',lambda:'lark-cli')
    monkeypatch.setattr(cli,'read_connection',lambda owner:{'last_verified_at':'today'})
    monkeypatch.setattr(cli,'profile',lambda owner:tmp_path)
    monkeypatch.setattr(service,'status',AsyncMock(return_value={'connected':True}))
    calls=[]
    async def run(owner,*args,**kwargs):
        calls.append((owner,args))
        if '+create' in args:
            content=args[args.index('--content')+1]
            assert Path(content[1:]).read_text()=='@/private/secret'
        return {'document':'result'}
    monkeypatch.setattr(cli,'run',run)
    tools={t.name:t for t in business_tools(7)}
    async def case():
        await tools['feishu_search_documents'].ainvoke({'query':'项目'})
        await tools['feishu_read_document'].ainvoke({'document':'abcdefghijk'})
        await tools['feishu_create_document'].ainvoke({'title':'需求','content':'@/private/secret'})
        count=len(calls)
        await tools['feishu_read_document'].ainvoke({'document':'file:///private/secret'})
        assert len(calls)==count
    asyncio.run(case())
    assert all(owner==7 for owner,args in calls)
    assert 'feishu_create_document' in GATED_TOOLS
    assert 'feishu_read_document' not in GATED_TOOLS
    assert not list(tmp_path.iterdir())
