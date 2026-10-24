"""业务异常 + 全局过滤器（异常归一为统一响应，不向客户端泄漏堆栈）。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .responses import ApiCode

log = logging.getLogger("api.exceptions")


class ApiError(Exception):
    """业务错误：携带 code / message / http status_code。"""

    def __init__(self, code: int, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常过滤器（docs/api-architecture.md §6）。"""

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 校验失败：code=1002，data 带字段级明细（供前端定位）
        return JSONResponse(
            status_code=422,
            content={
                "code": ApiCode.VALIDATION_ERROR,
                "message": "请求参数校验失败",
                "data": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        # 第三方/未覆盖的 HTTPException：按状态码映射，detail 不泄堆栈
        status = exc.status_code
        if status == 401:
            code, message = ApiCode.UNAUTHORIZED, "未登录或凭证无效"
        elif status == 403:
            code, message = ApiCode.FORBIDDEN, "无权限"
        elif status == 404:
            code, message = ApiCode.NOT_FOUND, "资源不存在"
        else:
            code, message = ApiCode.PARAM_ERROR, str(exc.detail or "请求错误")
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": message, "data": None},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # 兜底：完整堆栈只留服务端日志，客户端仅见 5000
        log.exception(
            "unhandled error: %s %s", request.method, request.url.path, exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": ApiCode.INTERNAL_ERROR,
                "message": "服务器内部错误",
                "data": None,
            },
        )
