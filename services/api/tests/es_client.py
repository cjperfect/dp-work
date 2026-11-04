"""通过官方客户端的 Node 接口注入 HTTP 替身，仍覆盖真实序列化和 Bulk helper。"""

import httpx
from elasticsearch import AsyncElasticsearch
from elastic_transport import BaseAsyncNode, ApiResponseMeta, HttpHeaders
from elastic_transport._node._base import NodeApiResponse


def client_factory(handler):
    class MockNode(BaseAsyncNode):
        async def perform_request(
            self, method, target, body=None, headers=None, request_timeout=None
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.base_url
            ) as client:
                response = await client.request(
                    method, target, content=body, headers=dict(headers or {})
                )
            meta = ApiResponseMeta(
                status=response.status_code,
                http_version="1.1",
                headers=HttpHeaders(
                    {**response.headers, "x-elastic-product": "Elasticsearch"}
                ),
                duration=0,
                node=self.config,
            )
            return NodeApiResponse(meta, response.content)

        async def close(self):
            pass

    return lambda **options: AsyncElasticsearch(node_class=MockNode, **options)
