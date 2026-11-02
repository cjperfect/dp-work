"""实际模型请求限流与查询向量缓存；Redis URL 仅由可信运行环境提供。"""
from contextlib import asynccontextmanager
import hashlib
import json
import logging
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.retry import Retry
from redis.backoff import NoBackoff
from ... import config
from .schemas import ModelError

log = logging.getLogger(__name__)
RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return {count, redis.call('TTL', KEYS[1])}
"""


def fingerprint(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@asynccontextmanager
async def connection():
    client = Redis.from_url(config.REDIS_URL, decode_responses=True,
        socket_connect_timeout=config.REDIS_TIMEOUT_SECONDS,
        socket_timeout=config.REDIS_TIMEOUT_SECONDS, retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
    try:
        yield client
    finally:
        await client.aclose()


def identity(model, base_url, api_key):
    # 原始凭证不进入 Redis key、值或日志；服务地址和凭证变更即切换缓存空间。
    return fingerprint(base_url, model, api_key)


async def permit(model, base_url, api_key):
    """按供应商配置及用户限额；包括 Agent 每一轮和子 Agent 实际请求。"""
    if not config.REDIS_URL:
        return
    from ...usage.ledger import context
    owner = context.get()[0]
    provider = identity(model, base_url, api_key)
    limits = [(provider, config.REDIS_MODEL_RPM)]
    if owner is not None:
        limits.insert(0, (fingerprint(owner, provider), config.REDIS_MODEL_USER_RPM))
    try:
        async with connection() as client:
            for scope, limit in limits:
                if limit <= 0:
                    continue
                count, ttl = await client.eval(RATE_SCRIPT, 1, config.REDIS_PREFIX + ':model-limit:' + scope)
                if count > limit:
                    raise ModelError('MODEL_RATE_LIMIT', f'模型调用过于频繁，请在 {max(1, ttl)} 秒后重试。')
    except (RedisError, OSError):
        if not config.REDIS_LIMIT_FAIL_OPEN:
            raise ModelError('MODEL_LIMIT_UNAVAILABLE', '模型限流服务暂不可用，请稍后重试。') from None
        log.warning('Redis 限流不可用，按配置放行模型请求。')


def query_key(text, profile):
    from ...usage.ledger import context
    return config.REDIS_PREFIX + ':query-vector:' + fingerprint(
        context.get()[0], profile, config.EMBEDDING_BASE_URL, config.EMBEDDING_MODEL,
        config.EMBEDDING_API_KEY, text)


async def cached_vector(text, profile):
    if not config.REDIS_URL or config.REDIS_CACHE_TTL_SECONDS <= 0:
        return None
    try:
        async with connection() as client:
            raw = await client.get(query_key(text, profile))
        return json.loads(raw) if raw else None
    except (RedisError, OSError, ValueError):
        log.warning('Redis 向量缓存未命中或暂不可用。')
        return None


async def cache_vector(text, profile, vector):
    if not config.REDIS_URL or config.REDIS_CACHE_TTL_SECONDS <= 0:
        return
    try:
        async with connection() as client:
            await client.set(query_key(text, profile), json.dumps(vector), ex=config.REDIS_CACHE_TTL_SECONDS)
    except (RedisError, OSError):
        log.warning('Redis 向量缓存写入失败，保留本次检索结果。')
