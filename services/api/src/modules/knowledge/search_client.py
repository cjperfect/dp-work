"""Elasticsearch 的中文 BM25 索引与查询适配。"""
import json
import math
import re
import ssl
from urllib.parse import urlsplit
import httpx
from src.core import config


class SearchError(ValueError):
    """可安全展示的搜索服务错误。"""


MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0, "analysis": {
        "char_filter": {"join_model_code": {"type": "pattern_replace", "pattern": "(?i)([a-z]+[0-9]+)[\\s_-]+([a-z]+)", "replacement": "$1$2"}},
        "analyzer": {"knowledge_text": {"type": "custom", "char_filter": ["join_model_code"], "tokenizer": "standard", "filter": ["cjk_width", "lowercase", "cjk_bigram"]}},
    }},
    "mappings": {"dynamic": "strict", "properties": {
        "owner_id": {"type": "long"}, "knowledge_base_id": {"type": "long"},
        "document_id": {"type": "keyword"}, "parent_id": {"type": "keyword"}, "task_id": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "knowledge_text"},
        "headings": {"type": "text", "analyzer": "knowledge_text"},
        "content": {"type": "text", "analyzer": "knowledge_text"},
    }},
}


class SearchClient:
    """只访问服务端配置的索引，不向浏览器提供 ES 凭证。"""
    def __init__(self, transport=None):
        self.transport = transport
        self.index = config.ELASTICSEARCH_INDEX
        url = urlsplit(config.ELASTICSEARCH_URL)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise SearchError("Elasticsearch 地址配置无效。")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,100}", self.index):
            raise SearchError("Elasticsearch 索引名配置无效。")

    async def request(self, method, path, *, allowed=(), **kwargs):
        """保留 TLS 校验并归一化上游错误。"""
        headers = kwargs.pop("headers", {})
        if config.ELASTICSEARCH_API_KEY:
            headers["Authorization"] = "ApiKey " + config.ELASTICSEARCH_API_KEY
        auth = None if config.ELASTICSEARCH_API_KEY or not config.ELASTICSEARCH_USERNAME else (
            config.ELASTICSEARCH_USERNAME, config.ELASTICSEARCH_PASSWORD)
        try:
            verify = ssl.create_default_context(cafile=config.ELASTICSEARCH_CA_FILE) if config.ELASTICSEARCH_CA_FILE else True
            async with httpx.AsyncClient(base_url=config.ELASTICSEARCH_URL, timeout=config.ELASTICSEARCH_TIMEOUT,
                headers=headers, auth=auth, verify=verify, follow_redirects=False, transport=self.transport) as client:
                response = await client.request(method, path, **kwargs)
            if response.status_code not in (*allowed, 200, 201):
                raise SearchError(f"Elasticsearch 请求失败（HTTP {response.status_code}）。")
            return response
        except (httpx.HTTPError, OSError) as cause:
            raise SearchError("无法连接 Elasticsearch，请检查服务与证书配置。") from cause

    async def ensure_index(self):
        """创建中文索引，并返回索引代号以检测删除重建。"""
        response = await self.request("GET", f"/{self.index}/_settings", allowed=(404,))
        if response.status_code == 404:
            created = await self.request("PUT", f"/{self.index}", json=MAPPING, allowed=(400,))
            if created.status_code == 400 and created.json().get("error", {}).get("type") != "resource_already_exists_exception":
                raise SearchError("关键词索引创建失败，请检查映射配置。")
            response = await self.request("GET", f"/{self.index}/_settings")
        try:
            return response.json()[self.index]["settings"]["index"]["uuid"]
        except (ValueError, KeyError, TypeError) as cause:
            raise SearchError("Elasticsearch 返回了无效的索引信息。") from cause

    async def purge_document(self, document_id):
        """清理该文档所有历史任务的子块。"""
        response = await self.request("POST", f"/{self.index}/_delete_by_query", params={"refresh": "true", "conflicts": "proceed"},
            json={"query": {"term": {"document_id": document_id}}})
        body = response.json()
        if body.get("timed_out") or body.get("failures"):
            raise SearchError("关键词旧索引清理未完成，将自动重试。")

    async def replace_document(self, document_id, records):
        """幂等替换子块，检查逐条写入错误并等待搜索可见。"""
        await self.purge_document(document_id)
        for offset in range(0, len(records), 256):
            lines = []
            for record in records[offset:offset + 256]:
                lines.append(json.dumps({"index": {"_id": record["id"]}}, ensure_ascii=False))
                lines.append(json.dumps({key: value for key, value in record.items() if key != "id"}, ensure_ascii=False))
            response = await self.request("POST", f"/{self.index}/_bulk", params={"refresh": "wait_for"},
                headers={"Content-Type": "application/x-ndjson"}, content=("\n".join(lines) + "\n").encode())
            if response.json().get("errors"):
                raise SearchError("部分关键词子块写入失败，将自动重试。")

    async def search(self, owner_id, base_ids, task_ids, query, limit):
        """先过滤账号、知识库和有效任务，再按 BM25 召回子块。"""
        if not task_ids:
            return []
        if len(task_ids) > 60000:
            raise SearchError("当前关键词检索范围过大，请缩小知识库范围。")
        response = await self.request("POST", f"/{self.index}/_search", json={
            "size": limit, "track_total_hits": False, "_source": False,
            "query": {"bool": {"filter": [
                {"term": {"owner_id": owner_id}}, {"terms": {"knowledge_base_id": base_ids}}, {"terms": {"task_id": task_ids}},
            ], "must": [{"multi_match": {"query": query, "fields": ["title^4", "headings^2", "content"],
                                         "type": "best_fields", "minimum_should_match": "30%"}}]}},
            "sort": [{"_score": "desc"}],
        })
        body = response.json()
        if body.get("timed_out") or body.get("_shards", {}).get("failed", 0):
            raise SearchError("Elasticsearch 检索未完整完成。")
        try:
            hits = [{"child_id": row["_id"], "score": float(row["_score"])} for row in body["hits"]["hits"]]
            if any(not math.isfinite(row["score"]) for row in hits):
                raise ValueError("invalid score")
            return hits
        except (ValueError, KeyError, TypeError) as cause:
            raise SearchError("Elasticsearch 返回了无效的检索结果。") from cause
