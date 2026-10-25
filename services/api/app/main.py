"""应用装配入口。启动：uvicorn app.main:app --port 8000。"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_router import api_router
from app.core import config
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.lifespan import lifespan
from app.middleware.request_context import RequestContextMiddleware


def create_app() -> FastAPI:
    """创建并配置 API 应用。"""
    configure_logging()
    application = FastAPI(
        title="DP Work 企业 Agent 平台 API",
        version="0.2.0",
        description=(
            "成功请求统一返回 HTTP 200，业务响应格式为 `{code, message, data}`。\n\n"
            "受保护接口通过右上角 **Authorize** 填写登录返回的 JWT token（无需 Bearer 前缀）。"
            "登录和注册的密码需先按公钥接口约定进行 JWE 加密，填写 `encrypted_password`。"
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        swagger_ui_parameters={"displayRequestDuration": True},
        openapi_tags=[
            {"name": "auth", "description": "账号注册、登录及当前用户信息"},
            {"name": "knowledge", "description": "知识库管理，需要登录"},
        ],
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
