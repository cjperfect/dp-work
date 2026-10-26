"""Agent 模型查询与流式执行转发，会话历史暂由客户端管理。"""
import json
from dataclasses import dataclass

import httpx
import anyio

from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from .schemas import AgentRequest
from app.modules.settings import service as settings_service
from app.modules.knowledge import rag, rag_access


def internal_headers():
    """获取 API 到 Sidecar 的内部认证信息。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise ApiError(ApiCode.INTERNAL_ERROR, "请先配置 API 与 Sidecar 的内部服务凭证。", 503)
    return {"X-Internal-Token": config.SIDECAR_INTERNAL_TOKEN}


async def check_response(response: httpx.Response):
    """将 Sidecar 的安全错误转换成统一业务响应。"""
    if response.status_code == 200:
        return
    message = "Agent 执行服务暂时不可用，请稍后重试。"
    try:
        detail = json.loads(await response.aread()).get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("message"), str):
            message = detail["message"][:300]
    except (ValueError, httpx.HTTPError):
        pass
    raise ApiError(ApiCode.INTERNAL_ERROR, message, 503)


async def list_models(owner_id: int | None = None) -> dict:
    """查询 Sidecar 的实际模型列表。"""
    if owner_id is not None:
        personal = await settings_service.runtime(owner_id, "model")
        if personal:
            return {"configured": True, "models": [{"id": personal["model"], "name": personal["model"]}]}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(config.SIDECAR_API_URL + "/internal/agents/models", headers=internal_headers())
            await check_response(response)
            return response.json()
    except (httpx.HTTPError, ValueError) as cause:
        raise ApiError(ApiCode.INTERNAL_ERROR, "无法读取 Agent 模型配置，请检查 Sidecar。", 503) from cause


@dataclass
class AgentStream:
    """持有上游连接，在结束或取消时释放。"""
    client: httpx.AsyncClient
    response: httpx.Response
    closed: bool = False

    async def close(self):
        if not self.closed:
            with anyio.CancelScope(shield=True):
                try:
                    await self.response.aclose()
                finally:
                    await self.client.aclose()
                    self.closed = True

    async def chunks(self):
        try:
            async for chunk in self.response.aiter_bytes():
                yield chunk
        except httpx.HTTPError:
            yield 'data: {"type":"error","code":"AGENT_DISCONNECTED","message":"Agent 连接中断，请重试。"}\n\n'.encode()
        finally:
            await self.close()


async def open_chat(body: AgentRequest, owner_id: int | None = None) -> AgentStream:
    """先连接并校验上游，再向前端开启事件流。"""
    payload = body.model_dump()
    if body.knowledge_base_ids:
        if owner_id is None:
            raise ApiError(ApiCode.UNAUTHORIZED, "请先登录。", 401)
        await rag.authorize_bases(owner_id, body.knowledge_base_ids)
        payload["retrieval_token"] = rag_access.issue_capability(owner_id, body.knowledge_base_ids)
    if owner_id is not None:
        personal = await settings_service.runtime(owner_id, "model")
        if personal:
            payload["runtime"] = personal
    headers = internal_headers()
    client = httpx.AsyncClient(timeout=httpx.Timeout(config.AGENT_REQUEST_TIMEOUT, connect=10), follow_redirects=False)
    try:
        request = client.build_request("POST", config.SIDECAR_API_URL + "/internal/agents/chat",
                                       headers=headers, json=payload)
        response = await client.send(request, stream=True)
        await check_response(response)
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise ApiError(ApiCode.INTERNAL_ERROR, "Agent 返回了无效的流式响应。", 502)
        return AgentStream(client, response)
    except BaseException as cause:
        await client.aclose()
        if isinstance(cause, httpx.HTTPError):
            raise ApiError(ApiCode.INTERNAL_ERROR, "无法连接 Agent 执行服务，请检查 Sidecar。", 503) from cause
        raise
