"""大模型调用的数据结构。"""
from dataclasses import dataclass, field
from ... import config


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = ""
    timeout: float = 180
    max_tokens: int = 8192


    @classmethod
    def from_env(cls) -> "ModelSettings":
        """读取 Sidecar 环境中的模型配置。"""
        return cls(api_key=config.ARK_API_KEY, model=config.ARK_MODEL, base_url=config.ARK_BASE_URL,
                   timeout=config.ARK_TIMEOUT_SECONDS, max_tokens=config.ARK_MAX_TOKENS)


class ModelError(Exception):
    """可安全展示的模型调用错误。"""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
