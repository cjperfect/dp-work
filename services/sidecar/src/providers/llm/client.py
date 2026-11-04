"""统一通过 LangChain 聊天模型调用文本与结构化输出。"""

import asyncio
from urllib.parse import urlparse
import httpx
from langchain_core.output_parsers import PydanticOutputParser
from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError
from ...usage.ledger import tracked, record_response
from .chat import build_chat_model
from .schemas import ModelError, ModelSettings


def validate(settings):
    if not settings.api_key or not settings.model or not settings.base_url:
        raise ModelError(
            "MODEL_NOT_CONFIGURED",
            "请配置 Sidecar 的 ARK_API_KEY、ARK_MODEL 和 ARK_BASE_URL。",
        )
    url = urlparse(settings.base_url)
    if (
        url.scheme != "https"
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ModelError(
            "MODEL_CONFIG_INVALID", "方舟模型地址必须使用不带凭证的 HTTPS 地址。"
        )


async def invoke(messages, settings, transport=None, schema=None):
    validate(settings)
    try:
        async with asyncio.timeout(settings.timeout):
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(settings.timeout, connect=10),
                follow_redirects=False,
            ) as asynchronous:
                with httpx.Client(
                    timeout=settings.timeout, follow_redirects=False
                ) as synchronous:
                    model = build_chat_model(settings, asynchronous, synchronous)
                    options = (
                        {"response_format": {"type": "json_object"}} if schema else {}
                    )
                    try:
                        raw = await model.ainvoke(messages, **options)
                    except BadRequestError as cause:
                        # 只有供应商明确拒绝 JSON 模式才降级，不重发其他失败请求。
                        if schema is None or not any(
                            value in str(cause.body).lower()
                            for value in ("response_format", "json_object")
                        ):
                            raise
                        raw = await model.ainvoke(messages)
                    metadata = raw.response_metadata
                    actual_model = metadata.get("model_name") or settings.model
                    await record_response(
                        {"usage": metadata.get("token_usage")}, actual_model
                    )
                    if metadata.get("finish_reason") != "stop":
                        raise ModelError(
                            "MODEL_INCOMPLETE",
                            "模型未返回完整结果，请调整输出长度或稍后重试。",
                        )
                    if not isinstance(raw.content, str) or not raw.content.strip():
                        raise ModelError(
                            "MODEL_INVALID_RESPONSE", "模型未返回有效的文本结果。"
                        )
                    if schema is not None and len(raw.content) > 18000:
                        raise ModelError(
                            "MODEL_INVALID_RESPONSE", "模型结构化输出过长。"
                        )
                    parsed = (
                        PydanticOutputParser(pydantic_object=schema).parse(raw.content)
                        if schema
                        else None
                    )
                    return raw.content.strip(), actual_model, parsed
    except ModelError:
        raise
    except (TimeoutError, APITimeoutError, httpx.TimeoutException):
        raise ModelError("MODEL_TIMEOUT", "模型调用超时，请稍后重试。") from None
    except APIStatusError as cause:
        code, message = {
            401: ("MODEL_AUTH_FAILED", "模型 API Key 无效，或无权访问该模型。"),
            403: ("MODEL_AUTH_FAILED", "模型 API Key 无效，或无权访问该模型。"),
            429: ("MODEL_RATE_LIMIT", "模型请求限流，请稍后重试。"),
        }.get(
            cause.status_code,
            ("MODEL_REQUEST_FAILED", "模型请求失败，请检查模型 ID 和服务配置。"),
        )
        raise ModelError(code, message, status_code=cause.status_code) from None
    except (APIConnectionError, httpx.HTTPError):
        raise ModelError("MODEL_UNAVAILABLE", "暂时无法连接模型服务。") from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ModelError(
            "MODEL_INVALID_RESPONSE",
            "模型未返回符合结构的有效结果。" if schema else "模型未返回有效结果。",
        ) from None


@tracked
async def complete(
    messages: list[dict], settings: ModelSettings, transport=None
) -> tuple[str, str]:
    text, model, _ = await invoke(messages, settings, transport)
    return text, model


@tracked
async def complete_structured(
    messages: list[dict], settings: ModelSettings, schema, transport=None
):
    _, _, value = await invoke(messages, settings, transport, schema)
    return value
