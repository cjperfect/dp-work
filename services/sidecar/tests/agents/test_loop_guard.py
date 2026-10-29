"""重复调用只拦截未执行的新操作，不误伤最终回答或实际进展。"""
import asyncio
from uuid import uuid4
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.tools import tool
from src.harness.loop_guard import check_loop
from src.providers.llm.schemas import ModelError, ModelSettings
from src import config
from src.agents import agent
from src.transport.handlers import AgentInput


def call(index, name='inspect_file', args=None):
    return {'name':name, 'args':args or {'path':'a.txt'}, 'id':str(index), 'type':'tool_call'}


def history(results=('same','same','same')):
    messages = [HumanMessage('检查文件')]
    for index, result in enumerate(results):
        messages.extend([AIMessage('',tool_calls=[call(index)]), ToolMessage(result, tool_call_id=str(index))])
    return messages


def test_same_args_and_different_results_or_operations_reset():
    messages = history()
    with pytest.raises(ModelError, match='阻止'):
        check_loop([*messages, AIMessage('',tool_calls=[call(4)])], 3, 5)
    check_loop([*messages, AIMessage('已检查完成')], 3, 5)
    check_loop([*messages, AIMessage('',tool_calls=[call(4,args={'path':'b.txt'})])], 3, 5)
    check_loop([*history(('one','two','three')), AIMessage('',tool_calls=[call(4)])], 3, 5)
    check_loop([*messages, HumanMessage('再次确认'), AIMessage('',tool_calls=[call(4)])], 3, 5)
    messages.extend([AIMessage('',tool_calls=[call(4,'edit_file')]), ToolMessage('changed',tool_call_id='4')])
    check_loop([*messages, AIMessage('',tool_calls=[call(5)])], 3, 5)


def test_parallel_duplicates_and_consecutive_errors_are_blocked():
    with pytest.raises(ModelError):
        check_loop([HumanMessage('检查'), AIMessage('',tool_calls=[call(i) for i in range(4)])], 3, 5)
    messages = [HumanMessage('检查')]
    for i in range(5):
        messages.extend([AIMessage('',tool_calls=[call(i,args={'path':str(i)})]), ToolMessage('failed',tool_call_id=str(i),status='error')])
    with pytest.raises(ModelError) as caught:
        check_loop([*messages, AIMessage('',tool_calls=[call(9)])], 3, 5)
    assert caught.value.code == 'AGENT_TOOL_ERROR_LIMIT'
    check_loop([*messages, AIMessage('工具失败，需要修复')], 3, 5)


def test_real_graph_stops_before_fourth_tool_and_keeps_error_code(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(config,'AGENT_REPEAT_LIMIT',3)
    calls = []
    @tool
    def inspect_file(path: str) -> str:
        """检查文件内容。"""
        calls.append(path)
        return 'same'
    class Model(FakeMessagesListChatModel):
        def bind_tools(self, *args, **kwargs): return self
    model = Model(responses=[AIMessage('',tool_calls=[call(i)]) for i in range(4)] + [AIMessage('完成')])
    monkeypatch.setattr(agent,'create_model',lambda *_:model)
    original_build = agent.build_agent
    monkeypatch.setattr(agent,'build_agent',lambda model, code, tools=None, *args, **kwargs: original_build(model, code, [inspect_file], *args, **kwargs))
    async def case():
        body=AgentInput(run_id=str(uuid4()),thread_id='loop-test',messages=[{'role':'user','content':'检查'}])
        events=[event async for event in agent.run_agent(body,ModelSettings(timeout=10))]
        assert events[-1]['type']=='error', events
        assert events[-1]['code']=='AGENT_REPEAT_LIMIT', events
        assert calls==['a.txt']*3
    asyncio.run(case())


def test_default_subagent_also_stops_repeating_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(config,'AGENT_REPEAT_LIMIT',3)
    calls = []
    @tool
    def inspect_file(path: str) -> str:
        """检查子任务资料。"""
        calls.append(path)
        return 'same'
    class Model(FakeMessagesListChatModel):
        def bind_tools(self, *args, **kwargs): return self
    model=Model(responses=[AIMessage('',tool_calls=[call('delegate','task',{'description':'检查文件','subagent_type':'general-purpose'})]),
        *[AIMessage('',tool_calls=[call(i)]) for i in range(4)], AIMessage('已停止重复检查')])
    monkeypatch.setattr(agent,'create_model',lambda *_:model)
    original_build = agent.build_agent
    monkeypatch.setattr(agent,'build_agent',lambda model, code, tools=None, *args, **kwargs: original_build(model, code, [inspect_file], *args, **kwargs))
    async def case():
        body=AgentInput(run_id=str(uuid4()),thread_id='child-loop-test',messages=[{'role':'user','content':'委派检查'}])
        events=[event async for event in agent.run_agent(body,ModelSettings(timeout=10))]
        assert calls == ['a.txt']*3, events
        assert events[-1]['type'] in ('done','error')
        if events[-1]['type']=='error': assert events[-1]['code']=='AGENT_REPEAT_LIMIT', events
    asyncio.run(case())


def test_argument_order_does_not_bypass_repeat_detection():
    messages=[HumanMessage('检查')]
    for i in range(3):
        messages.extend([AIMessage('',tool_calls=[call(i,args={'path':'a.txt','offset':0})]), ToolMessage('same',tool_call_id=str(i))])
    with pytest.raises(ModelError):
        check_loop([*messages, AIMessage('',tool_calls=[call(4,args={'offset':0,'path':'a.txt'})])],3,5)


def test_real_tool_errors_stop_before_sixth_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(config,'AGENT_TOOL_ERROR_LIMIT',5)
    class Model(FakeMessagesListChatModel):
        def bind_tools(self, *args, **kwargs): return self
    model=Model(responses=[AIMessage('',tool_calls=[call(i,'unknown_tool',{'path':str(i)})]) for i in range(6)])
    monkeypatch.setattr(agent,'create_model',lambda *_:model)
    async def case():
        body=AgentInput(run_id=str(uuid4()),thread_id='errors-test',messages=[{'role':'user','content':'检查'}])
        events=[event async for event in agent.run_agent(body,ModelSettings(timeout=10))]
        assert events[-1]['code']=='AGENT_TOOL_ERROR_LIMIT', events
        assert len([event for event in events if event['type']=='tool_result' and event['status']=='error'])==5
    asyncio.run(case())
