"""业务模块共用的 Sidecar 请求入口。"""
import httpx
from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from .transport import client as sidecar_client


async def sidecar(path: str, payload: dict | None = None, timeout: float = 25) -> dict:
    """调用可信执行服务，不转发上游敏感错误。"""
    if config.SIDECAR_TRANSPORT != "device" and not config.SIDECAR_INTERNAL_TOKEN:
        raise ApiError(ApiCode.INTERNAL_ERROR, "Sidecar 内部服务凭证尚未配置。", 503)
    try:
        async with sidecar_client(timeout=timeout) as client:
            response = await client.request("GET" if payload is None else "POST",
                config.SIDECAR_API_URL + "/internal" + path,
                headers={"X-Internal-Token": config.SIDECAR_INTERNAL_TOKEN}, json=payload)
        if response.status_code != 200:
            detail = response.json().get("detail", {})
            message = detail.get("message", "执行服务暂不可用，请检查 Sidecar 连接。") if isinstance(detail, dict) else "执行参数无效。"
            raise ApiError(ApiCode.PARAM_ERROR if response.status_code < 500 else ApiCode.INTERNAL_ERROR, message, response.status_code)
        return response.json()
    except (httpx.HTTPError, ValueError) as cause:
        raise ApiError(ApiCode.INTERNAL_ERROR, "无法连接 Sidecar，请稍后重试。", 503) from cause

