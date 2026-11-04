"""短连接适配 API 与 Celery 的独立事件循环，故障不泄露连接凭证。"""

import math
import time
from limits import RateLimitItemPerSecond
from limits.aio.storage import RedisStorage
from limits.aio.strategies import FixedWindowRateLimiter
import hashlib
import logging
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.retry import Retry
from redis.backoff import NoBackoff
from src.core import config

log = logging.getLogger(__name__)


def key(kind, identity):
    return (
        config.REDIS_PREFIX
        + ":"
        + kind
        + ":"
        + hashlib.sha256(str(identity).encode()).hexdigest()
    )


def connection(*, subscription=False):
    return Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=config.REDIS_TIMEOUT_SECONDS,
        socket_timeout=None if subscription else config.REDIS_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
    )


async def check_limit(kind, identity, limit, seconds=60):
    """返回需要等待的秒数；Redis 故障由调用方选择拒绝或放行。"""
    if not config.REDIS_URL or limit <= 0:
        return 0
    async with connection() as client:
        storage = RedisStorage(
            config.REDIS_URL,
            implementation="redispy",
            connection_pool=client.connection_pool,
            key_prefix=config.REDIS_PREFIX + ":limit",
        )
        limiter = FixedWindowRateLimiter(storage)
        rule = RateLimitItemPerSecond(limit, seconds)
        identity_key = key(kind, identity)
        if await limiter.hit(rule, identity_key):
            return 0
        window = await limiter.get_window_stats(rule, identity_key)
        return max(1, math.ceil(window.reset_time - time.time()))


async def publish(channel, payload):
    if not config.REDIS_URL or not config.REDIS_PUBSUB_ENABLED:
        return
    try:
        async with connection() as client:
            await client.publish(config.REDIS_PREFIX + ":events:" + channel, payload)
    except (RedisError, OSError):
        log.warning("Redis 通知不可用，保留 PostgreSQL 通知通道。")
