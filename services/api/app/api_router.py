"""路由注册中心，只汇总入口，不放业务逻辑。"""

from fastapi import APIRouter

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from app.modules.auth.router import router as auth_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.connectors.router import router as connectors_router

api_router = APIRouter()
for router in (auth_router, knowledge_router, connectors_router):
    api_router.include_router(router)


@api_router.get("/health")
async def health() -> dict:
    """检查服务健康状态。"""
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
    """处理未注册的接口请求。"""
    raise ApiError(ApiCode.NOT_FOUND, "资源不存在", 404)
