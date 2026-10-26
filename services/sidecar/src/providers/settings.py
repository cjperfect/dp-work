"""API 传入的个人服务覆盖配置，仅允许可信内部接口使用。"""
import asyncio
import time
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
import httpx
from .. import config
from .llm.schemas import ModelSettings
from .asr.doubao import DoubaoSettings, DoubaoRecognizer, AsrProviderError


class RuntimeConfig(BaseModel):
    """服务端间传递的个人配置，不向浏览器返回。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    provider: Literal["ark", "openai", "deepseek", "doubao"]
    base_url: str
    model: str = ""
    resource_id: str = "volc.seedasr.sauc.duration"
    speaker_info: bool = True
    api_key: SecretStr = Field(repr=False)

    @model_validator(mode="after")
    def validate_address(self):
        """避免个人配置成为任意内网请求入口。"""
        url = urlsplit(self.base_url)
        hosts = {"ark": "ark.cn-beijing.volces.com", "openai": "api.openai.com", "deepseek": "api.deepseek.com"}
        if url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
            raise ValueError("无效的服务地址")
        if self.provider == "doubao":
            if self.base_url != "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async":
                raise ValueError("无效的豆包语音地址")
        elif url.scheme != "https" or url.hostname != hosts[self.provider] or not self.model.strip():
            raise ValueError("无效的模型配置")
        if not self.api_key.get_secret_value().strip():
            raise ValueError("缺少 API Key")
        return self

    def llm(self):
        """转换为模型执行配置。"""
        if self.provider == "doubao":
            raise ValueError("语音配置不能用于模型服务")
        return ModelSettings(api_key=self.api_key.get_secret_value(), model=self.model, base_url=self.base_url,
                             timeout=config.ARK_TIMEOUT_SECONDS, max_tokens=config.ARK_MAX_TOKENS)

    def asr(self):
        """转换为语音执行配置。"""
        if self.provider != "doubao":
            raise ValueError("模型配置不能用于语音服务")
        return DoubaoSettings(api_key=self.api_key.get_secret_value(), base_url=self.base_url,
                              resource_id=self.resource_id, speaker_info=self.speaker_info)


def defaults():
    """公开平台默认参数及配置状态，隐藏密钥。"""
    return {"model": {"provider": "ark", "base_url": config.ARK_BASE_URL, "model": config.ARK_MODEL,
                      "configured": bool(config.ARK_API_KEY and config.ARK_MODEL and config.ARK_BASE_URL)},
            "asr": {"provider": "doubao", "base_url": config.VOLC_BASE_URL, "resource_id": config.VOLC_RESOURCE_ID,
                    "speaker_info": config.VOLC_SPEAKER_INFO, "configured": bool(config.VOLC_API_KEY)}}


async def test_connection(kind: str, override: RuntimeConfig | None):
    """测试实际模型回答或 ASR 握手，安全返回结果。"""
    started = time.monotonic()
    try:
        async with asyncio.timeout(20):
            if kind == "model":
                settings = override.llm() if override else ModelSettings.from_env()
                if not settings.api_key or not settings.model or not settings.base_url:
                    return {"ok": False, "message": "模型服务尚未配置。"}
                async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                    response = await client.post(settings.base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": "Bearer " + settings.api_key},
                        json={"model": settings.model, "messages": [{"role": "user", "content": "请只回复 OK"}], "max_tokens": 64, "stream": False})
                if response.status_code != 200:
                    return {"ok": False, "message": f"模型连接失败（HTTP {response.status_code}），请检查密钥、模型及服务地址。"}
                if not response.json().get("choices"):
                    return {"ok": False, "message": "模型服务返回了无效响应。"}
            else:
                recognizer = DoubaoRecognizer(override.asr() if override else None)
                try:
                    await recognizer.open()
                finally:
                    await recognizer.close()
        return {"ok": True, "message": "连接成功", "latency_ms": round((time.monotonic() - started) * 1000)}
    except AsrProviderError as cause:
        return {"ok": False, "message": str(cause)}
    except (TimeoutError, httpx.TimeoutException):
        return {"ok": False, "message": "连接超时，请检查配置或稍后重试。"}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "message": "连接失败，请检查服务地址、密钥和网络。"}
