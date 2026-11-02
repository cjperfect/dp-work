"""匿名 IP 与已鉴权用户分别限流，不信任客户端转发的 IP 头。"""
from starlette.responses import JSONResponse
from src.core import config
from src.infrastructure.redis.client import check_limit, RedisError


def response(status, message, retry=None):
    headers = {'Retry-After': str(retry)} if retry else {}
    return JSONResponse(status_code=status, headers=headers,
        content={'code': 4290 if status == 429 else 5000, 'message': message, 'data': None})


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not path.startswith('/api/') or scope.get('method') == 'OPTIONS':
            return await self.app(scope, receive, send)
        try:
            peer = scope.get('client') or ('unknown', 0)
            wait = await check_limit('ip', peer[0], config.REDIS_IP_RPM)
        except (RedisError, OSError):
            if not config.REDIS_LIMIT_FAIL_OPEN:
                return await response(503, '限流服务暂不可用，请稍后重试。')(scope, receive, send)
            wait = 0
        if wait:
            return await response(429, '请求过于频繁，请稍后重试。', wait)(scope, receive, send)
        await self.app(scope, receive, send)
