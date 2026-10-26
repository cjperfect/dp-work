"""大模型调用的数据结构。"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(default="", repr=False)
    model: str = "deepseek-v4-1-flash-261017"
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    timeout: float = 180
    max_tokens: int = 8192


class ModelError(Exception):
    """可安全展示的模型调用错误。"""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
