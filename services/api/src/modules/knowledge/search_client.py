"""Elasticsearch 的中文 BM25 索引与查询适配。"""

import math
import re
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from elasticsearch import AsyncElasticsearch, ApiError
from elasticsearch.helpers import async_bulk
from elastic_transport import TransportError
from src.core import config


class SearchError(ValueError):
    """可安全展示的搜索服务错误。"""


MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "char_filter": {
                "join_model_code": {
                    "type": "pattern_replace",
                    "pattern": "(?i)([a-z]+[0-9]+)[\\s_-]+([a-z]+)",
                    "replacement": "$1$2",
                }
            },
            "analyzer": {
                "knowledge_text": {
                    "type": "custom",
                    "char_filter": ["join_model_code"],
                    "tokenizer": "standard",
                    "filter": ["cjk_width", "lowercase", "cjk_bigram"],
                }
            },
        },
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            **{name: {"type": "long"} for name in ("owner_id", "knowledge_base_id")},
            **{
                name: {"type": "keyword"}
                for name in ("document_id", "parent_id", "task_id")
            },
            **{
                name: {"type": "text", "analyzer": "knowledge_text"}
                for name in ("title", "headings", "content")
            },
        },
    },
}


class SearchClient:
    """只访问服务端配置的索引，不向浏览器提供 ES 凭证。"""

    def __init__(self, client_factory=AsyncElasticsearch):
        self.client_factory = client_factory
        self.index = config.ELASTICSEARCH_INDEX
        url = urlsplit(config.ELASTICSEARCH_URL)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise SearchError("Elasticsearch 地址配置无效。")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,100}", self.index):
            raise SearchError("Elasticsearch 索引名配置无效。")

    @asynccontextmanager
    async def connection(self):
        """每个操作使用独立异步客户端，兼容 Celery 的独立事件循环。"""
        options = dict(
            hosts=config.ELASTICSEARCH_URL,
            request_timeout=config.ELASTICSEARCH_TIMEOUT,
            ca_certs=config.ELASTICSEARCH_CA_FILE or None,
            max_retries=0,
            retry_on_timeout=False,
        )
        if config.ELASTICSEARCH_API_KEY:
            options["api_key"] = config.ELASTICSEARCH_API_KEY
        elif config.ELASTICSEARCH_USERNAME:
            options["basic_auth"] = (
                config.ELASTICSEARCH_USERNAME,
                config.ELASTICSEARCH_PASSWORD,
            )
        try:
            async with self.client_factory(**options) as client:
                yield client
        except ApiError as cause:
            raise SearchError(
                f"Elasticsearch 请求失败（HTTP {cause.status_code}）。"
            ) from None
        except (
            TransportError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as cause:
            if isinstance(cause, SearchError):
                raise
            raise SearchError(
                "无法连接 Elasticsearch，请检查服务与证书配置。"
            ) from None

    async def ensure_index(self):
        async with self.connection() as client:
            response = await client.options(ignore_status=404).indices.get_settings(
                index=self.index
            )
            if response.meta.status == 404:
                created = await client.options(ignore_status=400).indices.create(
                    index=self.index, **MAPPING
                )
                if (
                    created.meta.status == 400
                    and created.body.get("error", {}).get("type")
                    != "resource_already_exists_exception"
                ):
                    raise SearchError("关键词索引创建失败，请检查映射配置。")
                response = await client.indices.get_settings(index=self.index)
            try:
                return response.body[self.index]["settings"]["index"]["uuid"]
            except (ValueError, KeyError, TypeError):
                raise SearchError("Elasticsearch 返回了无效的索引信息。") from None

    async def purge_document(self, document_id):
        async with self.connection() as client:
            response = await client.delete_by_query(
                index=self.index,
                refresh=True,
                conflicts="proceed",
                query={"term": {"document_id": document_id}},
            )
            if response.body.get("timed_out") or response.body.get("failures"):
                raise SearchError("关键词旧索引清理未完成，将自动重试。")

    async def replace_document(self, document_id, records):
        await self.purge_document(document_id)
        if not records:
            return
        actions = (
            {
                "_op_type": "index",
                "_index": self.index,
                "_id": row["id"],
                "_source": {key: value for key, value in row.items() if key != "id"},
            }
            for row in records
        )
        async with self.connection() as client:
            count, errors = await async_bulk(
                client,
                actions,
                chunk_size=256,
                refresh="wait_for",
                max_retries=0,
                raise_on_error=False,
            )
            if errors or count != len(records):
                raise SearchError("部分关键词子块写入失败，将自动重试。")

    async def search(self, owner_id, base_ids, task_ids, query, limit):
        """先过滤账号、知识库和有效任务，再按 BM25 召回子块。"""
        if not task_ids:
            return []
        if len(task_ids) > 60000:
            raise SearchError("当前关键词检索范围过大，请缩小知识库范围。")
        async with self.connection() as client:
            response = await client.search(
                index=self.index,
                size=limit,
                track_total_hits=False,
                source=False,
                query={
                    "bool": {
                        "filter": [
                            {"term": {"owner_id": owner_id}},
                            {"terms": {"knowledge_base_id": base_ids}},
                            {"terms": {"task_id": task_ids}},
                        ],
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["title^4", "headings^2", "content"],
                                    "type": "best_fields",
                                    "minimum_should_match": "30%",
                                }
                            }
                        ],
                    }
                },
                sort=[{"_score": "desc"}],
            )
        body = response.body
        if body.get("timed_out") or body.get("_shards", {}).get("failed", 0):
            raise SearchError("Elasticsearch 检索未完整完成。")
        try:
            hits = [
                {"child_id": row["_id"], "score": float(row["_score"])}
                for row in body["hits"]["hits"]
            ]
            if any(not math.isfinite(row["score"]) for row in hits):
                raise ValueError("invalid score")
            return hits
        except (ValueError, KeyError, TypeError) as cause:
            raise SearchError("Elasticsearch 返回了无效的检索结果。") from cause
