"""统一响应协议：所有接口输出 { code, message, data }。

错误码段位（对齐 docs/api-architecture.md §3.3）：
- 0      成功
- 1xxx   通用 / 请求错误（1001 参数错误 / 1002 校验失败 / 1003 资源不存在）
- 2xxx   认证 / 授权（2001 未登录 / 2002 token 过期 / 2003 无权限 / 2004 凭证错误）
- 3xxx   业务规则（3001 会议不存在 / 3002 纪要未生成 / 3003 状态冲突）
- 5xxx   服务端（5000 内部错误）
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiCode:
    OK = 0
    PARAM_ERROR = 1001
    VALIDATION_ERROR = 1002
    NOT_FOUND = 1003
    UNAUTHORIZED = 2001
    TOKEN_EXPIRED = 2002
    FORBIDDEN = 2003
    BAD_CREDENTIALS = 2004
    MEETING_NOT_FOUND = 3001
    MINUTES_NOT_READY = 3002
    STATE_CONFLICT = 3003
    INTERNAL_ERROR = 5000


class ApiResponse(BaseModel, Generic[T]):
    code: int = ApiCode.OK
    message: str = "ok"
    data: T | None = None


def ok(data: T | None = None, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse(code=ApiCode.OK, message=message, data=data)
