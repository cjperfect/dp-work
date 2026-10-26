"""父子分块及方舟向量协议使用受控响应验证。"""
import asyncio
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from src import config
from src.knowledge.rag.chunking import split_document
from src.knowledge.rag.embedding import ArkEmbeddings, EmbeddingError, profile
from src.knowledge.rag.tool import knowledge_tool


def test_parent_child_chunks_preserve_context_and_headings():
    content = '# 报销制度\n\n## 差旅\n\n' + '\n\n'.join(f'第{i}项差旅报销规定：提交票据后由部门负责人审核。' * 8 for i in range(40))
    parents = split_document(content)
    assert len(parents) > 1
    assert any(len(parent['children']) > 1 for parent in parents)
    for parent in parents:
        assert len(parent['content']) <= 2000
        assert parent['metadata']['headings'][0] == '报销制度'
        for child in parent['children']:
            assert len(child['content']) <= 500
            assert child['content'] in parent['content']
            assert parent['content'][child['start']:child['start'] + len(child['content'])] == child['content']
    with pytest.raises(EmbeddingError):
        split_document('  ')


def test_page_numbers_are_only_kept_when_text_matches():
    assert split_document('文档内容', [{'page_number': 3, 'content': '文档内容'}])[0]['metadata']['page'] == 3
    assert 'page' not in split_document('人工修改后的内容', [{'page_number': 3, 'content': '原文内容'}])[0]['metadata']


def test_embedding_does_not_merge_children_and_distinguishes_query_instruction(monkeypatch):
    requests = []
    active, maximum = 0, 0
    async def handler(request):
        nonlocal active, maximum
        active += 1; maximum = max(maximum, active)
        await asyncio.sleep(.001)
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers['Authorization'] == 'Bearer fixture-key'
        active -= 1
        return httpx.Response(200, json={'data': {'embedding': [1.0] + [0.0] * 1023}})
    original = httpx.AsyncClient
    monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'fixture-key')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    async def case():
        values = await ArkEmbeddings().aembed_documents(['段落' + str(index) for index in range(7)])
        assert len(values) == 7 and maximum <= 4
        assert all(len(body['input']) == 1 and body['dimensions'] == 1024 for body in requests)
        await ArkEmbeddings().aembed_query('差旅怎么报销？')
        assert 'Target_modality' in requests[-1]['instructions']
        assert 'Compress the text' in requests[0]['instructions']
    asyncio.run(case())


def test_bad_dimensions_and_upstream_errors_are_safe(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'fixture-key')
    for response in (httpx.Response(200, json={'data': {'embedding': [1, 2]}}), httpx.Response(401, json={'error': 'sensitive-upstream-body'})):
        monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: response), **kwargs))
        with pytest.raises(EmbeddingError) as error:
            asyncio.run(ArkEmbeddings().aembed_query('test'))
        assert 'sensitive-upstream-body' not in str(error.value) and 'fixture-key' not in str(error.value)


def test_tool_is_bound_to_server_capability_and_returns_sources(monkeypatch):
    seen = []
    async def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'code': 0, 'data': [{'title': '报销规定', 'content': '完整父块', 'url': '/knowledge/server-1/files/doc'}]})
    monkeypatch.setattr(ArkEmbeddings, 'aembed_query', AsyncMock(return_value=[1.0] + [0.0] * 1023))
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tool = knowledge_tool('scoped-server-token', client)
            result = await tool.ainvoke({'query': '怎么报销？'})
            assert result['sources'][0]['content'] == '完整父块'
            assert list(tool.args) == ['query']
    asyncio.run(case())
    assert seen[0]['capability'] == 'scoped-server-token'
    assert seen[0]['profile'] == profile()


def test_tool_preserves_index_not_ready_diagnostic(monkeypatch):
    monkeypatch.setattr(ArkEmbeddings, 'aembed_query', AsyncMock(return_value=[1.0] + [0.0] * 1023))
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'code': 0, 'data': {
            'sources': [], 'coverage': {'total': 2, 'ready': 0, 'not_ready': 2}, 'message': '文档尚未向量化，请先向量化。'}}))) as client:
            result = await knowledge_tool('fixture-capability', client).ainvoke({'query': 'N6mini电池容量'})
            assert result['sources'] == [] and result['coverage']['ready'] == 0
            assert '向量化' in result['message'] and '不能断言' in result['notice']
    asyncio.run(case())
