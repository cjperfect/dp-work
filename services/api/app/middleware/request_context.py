"""拦截器：RequestContext 中间件 —— X-Request-ID、计时、访问日志、上下文注入。

docs/api-architecture.md §5.1。认证在守卫层完成，中间件只做横切观察。

实现说明：使用纯 ASGI 中间件（而非 starlette BaseHTTPMiddleware），
保证业务在**同一事件循环**内执行——asyncpg 连接池绑定创建时的 loop，
BaseHTTPMiddleware 的独立任务会触发 "attached to a different loop"。
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("api.access")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        # 经 scope["state"] 注入（request.state 基于 scope state 映射）
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status_sent: dict[str, int | None] = {"code": None}

        def send_with_rid(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                status_sent["code"] = message.get("status")
                headers = message.setdefault("headers", [])
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
            return send(message)

        try:
            await self.app(scope, receive, send_with_rid)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log.warning(
                "%s %s %s %.1fms rid=%s",
                request.method,
                request.url.path,
                status_sent["code"] or 500,
                duration_ms,
                request_id,
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        user_id = state.get("user_id", "-")
        log.info(
            "%s %s %s %.1fms rid=%s uid=%s",
            request.method,
            request.url.path,
            status_sent["code"] or "-",
            duration_ms,
            request_id,
            user_id,
        )
