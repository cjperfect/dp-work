"""个人服务配置协议。"""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

MODEL_HOSTS = {"ark": "ark.cn-beijing.volces.com", "openai": "api.openai.com", "deepseek": "api.deepseek.com"}
ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"


class ServiceConfig(BaseModel):
    """个人配置；不提交密钥表示保留原值。"""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    provider: Literal["ark", "openai", "deepseek", "doubao"]
    base_url: str = Field(max_length=500)
    model: str = Field(default="", max_length=128)
    resource_id: str = Field(default="volc.seedasr.sauc.duration", max_length=128)
    speaker_info: bool = True
    api_key: SecretStr | None = None
    clear_api_key: bool = False

    @model_validator(mode="after")
    def validate_service(self):
        """校验服务地址及必填项。"""
        self.base_url = self.base_url.strip().rstrip("/")
        self.model = self.model.strip()
        self.resource_id = self.resource_id.strip()
        url = urlsplit(self.base_url)
        if url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
            raise ValueError("服务地址不能包含凭证、查询参数或自定义端口。")
        if self.provider == "doubao":
            if self.base_url != ASR_URL:
                raise ValueError("请使用豆包流式语音识别大模型地址。")
            if self.enabled and not self.resource_id:
                raise ValueError("请输入语音资源 ID。")
        elif url.scheme != "https" or url.hostname != MODEL_HOSTS[self.provider]:
            raise ValueError("请选择服务商对应的官方 HTTPS 地址。")
        elif self.enabled and not self.model:
            raise ValueError("请输入模型 ID。")
        if self.api_key is not None and (not self.api_key.get_secret_value().strip() or len(self.api_key.get_secret_value()) > 8192):
            raise ValueError("API Key 不能为空。")
        if self.clear_api_key and self.api_key is not None:
            raise ValueError("不能同时替换和清除 API Key。")
        return self
