"""统一接口响应结构与业务码。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiCode:
    """业务响应码。"""
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
    """统一接口响应结构。"""
    code: int = ApiCode.OK
    message: str = "ok"
    data: T | None = None


def ok(data: T | None = None, message: str = "ok") -> ApiResponse[T]:
    """生成成功响应。"""
    return ApiResponse(code=ApiCode.OK, message=message, data=data)
