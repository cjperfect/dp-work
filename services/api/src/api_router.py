"""路由注册中心，只汇总入口，不放业务逻辑。"""

from fastapi import APIRouter

from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.modules.auth.router import router as auth_router
from src.modules.agents.router import router as agents_router
from src.modules.settings.router import router as settings_router
from src.modules.knowledge.router import router as knowledge_router
from src.modules.knowledge.rag_router import router as rag_router
from src.modules.connectors.router import router as connectors_router

from src.modules.meetings.router import router as meetings_router

from src.modules.devices.router import router as devices_router

api_router = APIRouter()
from src.modules.skills.router import router as skills_router

api_router.include_router(devices_router)
api_router.include_router(skills_router)
for router in (auth_router, knowledge_router, connectors_router, meetings_router, agents_router, settings_router, rag_router):
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
