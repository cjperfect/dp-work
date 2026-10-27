"""可复用的 HTTP 装饰器，按用途拆分文件。"""

from .auth import require_user

__all__ = ["require_user"]
