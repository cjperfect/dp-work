"""路由注册中心，只汇总入口，不放业务逻辑。"""

from fastapi import APIRouter

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from app.modules.auth.router import router as auth_router
from app.modules.meetings.router import placeholder_router
from app.modules.meetings.router import router as meetings_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
for router in (auth_router, users_router, meetings_router, placeholder_router):
    api_router.include_router(router)


@api_router.get("/health")
async def health() -> dict:
    try:
        healthy = await session.is_healthy()
        return {"ok": healthy, "db": "up" if healthy else "down"}
    except Exception:  # noqa: BLE001 -- 健康检查将所有连接故障统一报告为 down
        return {"ok": False, "db": "down"}


@api_router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
async def not_found(full_path: str) -> None:
    raise ApiError(ApiCode.NOT_FOUND, "资源不存在", 404)
