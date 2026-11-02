"""短连接适配 API 与 Celery 的独立事件循环，故障不泄露连接凭证。"""
from contextlib import asynccontextmanager
import hashlib
import logging
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.retry import Retry
from redis.backoff import NoBackoff
from src.core import config

log = logging.getLogger(__name__)

# INCR 与过期设置必须原子执行，窗口从首个请求开始。
RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


def key(kind, identity):
    return config.REDIS_PREFIX + ':' + kind + ':' + hashlib.sha256(str(identity).encode()).hexdigest()


@asynccontextmanager
async def connection(*, subscription=False):
    client = Redis.from_url(config.REDIS_URL, decode_responses=True,
        socket_connect_timeout=config.REDIS_TIMEOUT_SECONDS,
        socket_timeout=None if subscription else config.REDIS_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
    try:
        yield client
    finally:
        await client.aclose()


async def check_limit(kind, identity, limit, seconds=60):
    """返回需要等待的秒数；Redis 故障由调用方选择拒绝或放行。"""
    if not config.REDIS_URL or limit <= 0:
        return 0
    async with connection() as client:
        count, ttl = await client.eval(RATE_SCRIPT, 1, key('limit:' + kind, identity), seconds)
    return max(1, int(ttl)) if count > limit else 0


async def publish(channel, payload):
    if not config.REDIS_URL or not config.REDIS_PUBSUB_ENABLED:
        return
    try:
        async with connection() as client:
            await client.publish(config.REDIS_PREFIX + ':events:' + channel, payload)
    except (RedisError, OSError):
        log.warning('Redis 通知不可用，保留 PostgreSQL 通知通道。')
