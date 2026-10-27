"""混合检索排序和 ES 协议边界。"""
import asyncio
import json
import httpx
import pytest
from src.core import config
from src.modules.knowledge.hybrid import fuse_ranks
from src.modules.knowledge.search_client import SearchClient, SearchError


def test_rrf_uses_rank_and_deduplicates_each_channel():
    hits = fuse_ranks([{'child_id': 'a', 'score': .99}, {'child_id': 'b', 'score': .01}],
                     [{'child_id': 'b', 'score': 2000}, {'child_id': 'a', 'score': 1}])
    assert [h['child_id'] for h in hits] == ['a', 'b']
    assert hits[0]['score'] == pytest.approx(1 / 61 + 1 / 62)
    assert hits[0]['channels'] == ['keyword', 'vector']
    assert fuse_ranks([{'child_id': 'a', 'score': 1}] * 2, [])[0]['score'] == 1 / 61


def test_keyword_filters_and_bulk_protocol(monkeypatch):
    requests = []
    def upstream(request):
        requests.append(request)
        if request.url.path.endswith('/_search'):
            return httpx.Response(200, json={'hits': {'hits': [{'_id': 'child', '_score': 8.5}]}})
        return httpx.Response(200, json={'errors': False})
    monkeypatch.setattr(config, 'ELASTICSEARCH_API_KEY', 'test-only-key')
    async def case():
        client = SearchClient(transport=httpx.MockTransport(upstream))
        assert await client.search(7, [11], ['task'], 'N6 mini 电池', 50) == [{'child_id': 'child', 'score': 8.5}]
        body = json.loads(requests[0].content)
        assert body['query']['bool']['filter'] == [{'term': {'owner_id': 7}}, {'terms': {'knowledge_base_id': [11]}}, {'terms': {'task_id': ['task']}}]
        assert requests[0].headers['authorization'] == 'ApiKey test-only-key'
        await client.replace_document('doc', [{'id': 'child', 'content': '中文', 'document_id': 'doc'}])
        lines = requests[-1].content.decode().splitlines()
        assert json.loads(lines[0]) == {'index': {'_id': 'child'}}
        assert json.loads(lines[1]) == {'content': '中文', 'document_id': 'doc'}
        assert requests[-1].content.endswith(b'\n')
        assert requests[-1].url.params['refresh'] == 'wait_for'
    asyncio.run(case())


@pytest.mark.parametrize('body', [{'errors': True}, {'timed_out': True}, {'_shards': {'failed': 1}}, {'hits': {'hits': [{'_id': 'x', '_score': 'NaN'}]}}])
def test_partial_and_invalid_es_responses_fail_closed(body):
    async def case():
        client = SearchClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
        with pytest.raises(SearchError):
            if 'errors' in body:
                await client.replace_document('doc', [{'id': 'x'}])
            else:
                await client.search(1, [1], ['task'], '问题', 4)
    asyncio.run(case())


def test_es_error_does_not_expose_upstream_secrets():
    async def case():
        client = SearchClient(transport=httpx.MockTransport(lambda _: httpx.Response(401, text='secret upstream credential')))
        with pytest.raises(SearchError) as error:
            await client.search(1, [1], ['task'], '问题', 4)
        assert 'secret' not in str(error.value)
    asyncio.run(case())
