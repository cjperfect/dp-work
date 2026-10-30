"""火山方舟 Chat Completions 客户端。"""
import asyncio
from urllib.parse import urlparse
import httpx
from ...usage.ledger import tracked, record_response
from .schemas import ModelError, ModelSettings


@tracked
async def complete(messages: list[dict], settings: ModelSettings, transport=None) -> tuple[str, str]:
    """调用方舟并校验完整的文本结果，不回传上游原始错误。"""
    if not settings.api_key or not settings.model or not settings.base_url:
        raise ModelError("MODEL_NOT_CONFIGURED", "请配置 Sidecar 的 ARK_API_KEY、ARK_MODEL 和 ARK_BASE_URL。")
    url = urlparse(settings.base_url)
    if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
        raise ModelError("MODEL_CONFIG_INVALID", "方舟模型地址必须使用不带凭证的 HTTPS 地址。")
    try:
        async with asyncio.timeout(settings.timeout):
            async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(settings.timeout, connect=10), follow_redirects=False) as client:
                response = await client.post(settings.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    json={"model": settings.model, "messages": messages, "stream": False, "max_tokens": settings.max_tokens})
    except (TimeoutError, httpx.TimeoutException) as cause:
        raise ModelError("MODEL_TIMEOUT", "方舟模型调用超时，请稍后重试。") from cause
    except httpx.HTTPError as cause:
        raise ModelError("MODEL_UNAVAILABLE", "暂时无法连接方舟模型服务。") from cause
    if response.status_code in (401, 403):
        raise ModelError("MODEL_AUTH_FAILED", "方舟 API Key 无效，或无权访问该模型。")
    if response.status_code == 429:
        raise ModelError("MODEL_RATE_LIMIT", "方舟模型请求限流，请稍后重试。")
    if response.status_code >= 400 or response.is_redirect:
        raise ModelError("MODEL_REQUEST_FAILED", "方舟模型请求失败，请检查模型 ID 和服务配置。")
    try:
        body = response.json()
        await record_response(body, body.get("model") or settings.model)
        choice = body["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ModelError("MODEL_INCOMPLETE", "模型未返回完整纪要，请调整输出长度或稍后重试。")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty content")
        return content.strip(), body.get("model") or settings.model
    except (ValueError, KeyError, IndexError, TypeError) as cause:
        raise ModelError("MODEL_INVALID_RESPONSE", "方舟模型未返回有效的文本纪要。") from cause
