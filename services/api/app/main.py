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
    configure_logging()
    application = FastAPI(title="dp-work api", version="0.2.0", lifespan=lifespan)
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
