"""供应商思考字段、流式事件及最终回答保持分离。"""
import asyncio
import json
import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from src.providers.llm.chat import ReasoningChatOpenAI, reasoning_text


def test_provider_fields_survive_conversion_and_tool_follow_up():
    model=ReasoningChatOpenAI(model='fixture',api_key='fixture',base_url='https://fixture.invalid/v1')
    raw={'choices':[{'delta':{'role':'assistant','content':'','reasoning_content':'先查看资料','encrypted_content':'opaque'}}]}
    chunk=model._convert_chunk_to_generation_chunk(raw,AIMessageChunk,None)
    assert reasoning_text(chunk.message)=='先查看资料'
    message=AIMessage('',additional_kwargs=chunk.message.additional_kwargs,tool_calls=[{'name':'read_file','args':{'path':'a.txt'},'id':'c1','type':'tool_call'}])
    payload=model._get_request_payload([HumanMessage('问题'),message,ToolMessage('资料',tool_call_id='c1')])
    assert payload['messages'][1]['reasoning_content']=='先查看资料'
    assert payload['messages'][1]['encrypted_content']=='opaque'
    assert reasoning_text(AIMessage('',additional_kwargs={'encrypted_content':'opaque'}))==''
    assert reasoning_text(AIMessage([{'type':'reasoning','summary':[{'text':'公开摘要'}]}]))=='公开摘要'


def test_actual_openai_stream_retains_reasoning_deltas():
    events=[{'choices':[{'index':0,'delta':{'role':'assistant','reasoning_content':'先检查'}}]},
            {'choices':[{'index':0,'delta':{'content':'最终回答'},'finish_reason':'stop'}]}]
    data=''.join('data: '+json.dumps(e,ensure_ascii=False)+'\n\n' for e in events)+'data: [DONE]\n\n'
    async def case():
        transport=httpx.MockTransport(lambda request:httpx.Response(200,text=data,headers={'content-type':'text/event-stream'}))
        async with httpx.AsyncClient(transport=transport) as client:
            model=ReasoningChatOpenAI(model='fixture',api_key='fixture',base_url='https://fixture.invalid/v1',http_async_client=client)
            chunks=[chunk async for chunk in model.astream('测试')]
            assert ''.join(reasoning_text(chunk) for chunk in chunks)=='先检查'
            assert ''.join(chunk.content for chunk in chunks)=='最终回答'
    asyncio.run(case())


def test_graph_emits_separate_reasoning_and_answer(monkeypatch,tmp_path):
    from src import config
    from src.agents import agent
    from src.providers.llm.schemas import ModelSettings
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    monkeypatch.setattr(config,'WORKSPACE_DIR',tmp_path/'workspace')
    class Model(FakeMessagesListChatModel):
        def bind_tools(self,*args,**kwargs):return self
    monkeypatch.setattr(agent,'create_model',lambda *_:Model(responses=[AIMessage('最终回答',additional_kwargs={'reasoning_content':'先核对资料'})]))
    async def case():
        body=agent.AgentRequest(thread_id='thought-test',messages=[{'role':'user','content':'问题'}])
        events=[event async for event in agent.run_agent(body,ModelSettings(timeout=10))]
        assert events[-1]['type']=='done',events
        assert events[-1]['content']=='最终回答'
        assert ''.join(e['text'] for e in events if e['type']=='reasoning')=='先核对资料'
        assert [e['type'] for e in events].index('reasoning_end') < [e['type'] for e in events].index('delta')
    asyncio.run(case())
