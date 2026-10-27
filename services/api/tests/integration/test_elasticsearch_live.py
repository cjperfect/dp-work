"""显式启用真实 ES 的隔离索引测试，不访问应用索引。"""
import asyncio
import os
from uuid import uuid4
import pytest
from src.core import config
from src.modules.knowledge.search_client import SearchClient


def test_real_chinese_bm25_model_code_and_version_filters(monkeypatch):
    url = os.environ.get('TEST_ELASTICSEARCH_URL')
    if not url:
        pytest.skip('设置 TEST_ELASTICSEARCH_URL 以启用真实 ES 测试')
    index = 'dp-work-test-' + uuid4().hex
    monkeypatch.setattr(config, 'ELASTICSEARCH_URL', url)
    monkeypatch.setattr(config, 'ELASTICSEARCH_INDEX', index)
    monkeypatch.setattr(config, 'ELASTICSEARCH_API_KEY', os.environ.get('TEST_ELASTICSEARCH_API_KEY', ''))
    monkeypatch.setattr(config, 'ELASTICSEARCH_USERNAME', '')
    monkeypatch.setattr(config, 'ELASTICSEARCH_PASSWORD', '')
    async def case():
        client = SearchClient()
        try:
            assert await client.ensure_index()
            def record(key, owner, task):
                return {'id': key, 'document_id': 'fixture', 'parent_id': 'parent', 'owner_id': owner,
                    'knowledge_base_id': 1, 'task_id': task, 'title': 'N6-mini 产品手册', 'headings': '电池',
                    'content': 'N6\nmini 的电池容量为 1800mAh，支持快速充电。'}
            await client.replace_document('fixture', [record('current', 1, 'active'), record('foreign', 2, 'active'), record('stale', 1, 'old')])
            for query in ['N6mini电池容量', 'N6 mini', 'N6-mini', '电池容量']:
                hits = await client.search(1, [1], ['active'], query, 10)
                assert [row['child_id'] for row in hits] == ['current'], query
            await client.replace_document('fixture', [])
            assert await client.search(1, [1], ['active'], '电池', 10) == []
        finally:
            await client.request('DELETE', '/' + index, allowed=(404,))
    asyncio.run(case())
