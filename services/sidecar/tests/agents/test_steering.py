"""引导在同一张图内生效，工具结果不丢失，不重新执行已有工具。"""
import asyncio
from uuid import uuid4
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from src import config
from src.agents.agent import agent_events
from src.harness.approvals import checkpoint
from src.harness.steering import active_run, deliver, INBOXES
from src.transport.handlers import AgentInput
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel


class Model(FakeMessagesListChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def test_steering_keeps_tool_result_and_same_run(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path/'workspace')
    async def case():
        started, release = asyncio.Event(), asyncio.Event()
        calls, seen = [], []
        @tool
        async def inspect_source() -> str:
            """读取待处理资料。"""
            calls.append('tool')
            started.set()
            await release.wait()
            return 'TOOL_RESULT_SAVED'
        class CapturingModel(Model):
            async def _agenerate(self, messages, **kwargs):
                seen.append(list(messages))
                return await super()._agenerate(messages, **kwargs)
        model = CapturingModel(responses=[
            AIMessage('', tool_calls=[{'name':'inspect_source','args':{},'id':'inspect','type':'tool_call'}]),
            AIMessage('按补充要求使用黑色按钮')])
        run_id, message_id = str(uuid4()), str(uuid4())
        body = AgentInput(run_id=run_id, thread_id='steering-test', workspace_owner_id=7,
            messages=[{'role':'user','content':'创建页面'}])
        async with checkpoint(run_id) as saved:
            with active_run(run_id, 7, body.thread_id):
                async def collect(): return [event async for event in agent_events(body, model, [inspect_source], saved.saver)]
                task = asyncio.create_task(collect())
                await asyncio.wait_for(started.wait(), 5)
                with pytest.raises(ValueError): deliver(run_id, 8, body.thread_id, message_id, '越权')
                deliver(run_id, 7, body.thread_id, message_id, '按钮改成黑色')
                deliver(run_id, 7, body.thread_id, message_id, '按钮改成黑色')
                release.set()
                events = await asyncio.wait_for(task, 5)
        assert events[-1]['type'] == 'done', events
        assert events[-1]['run_id'] == run_id
        assert len([event for event in events if event['type'] == 'steering']) == 1
        assert calls == ['tool']
        assert any(isinstance(message, ToolMessage) and message.content == 'TOOL_RESULT_SAVED' for message in seen[-1])
        assert sum(message.content == '按钮改成黑色' for message in seen[-1]) == 1
        assert run_id not in INBOXES
        with pytest.raises(ValueError): deliver(run_id, 7, body.thread_id, str(uuid4()), '结束后不能投递')
    asyncio.run(case())


def test_steering_arriving_during_final_model_call_starts_another_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path/'workspace')
    async def case():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        class PausedModel(Model):
            async def _agenerate(self, messages, **kwargs):
                calls.append(list(messages))
                if len(calls) == 1:
                    started.set()
                    await release.wait()
                return await super()._agenerate(messages, **kwargs)
        model = PausedModel(responses=[AIMessage('原来的回答'), AIMessage('收到补充要求后的回答')])
        run_id = str(uuid4())
        body = AgentInput(run_id=run_id, thread_id='steering-test', messages=[{'role':'user','content':'原问题'}])
        async with checkpoint(run_id) as saved:
            with active_run(run_id, 1, body.thread_id):
                async def collect(): return [event async for event in agent_events(body, model, checkpointer=saved.saver)]
                task = asyncio.create_task(collect())
                await asyncio.wait_for(started.wait(), 5)
                deliver(run_id, 1, body.thread_id, str(uuid4()), '补充要求')
                release.set()
                events = await asyncio.wait_for(task, 5)
        assert len(calls) == 2
        assert events[-1]['type'] == 'done', events
        assert events[-1]['content'] == '收到补充要求后的回答'
        assert any(message.content == '补充要求' for message in calls[-1])
    asyncio.run(case())
