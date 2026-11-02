"""提交后 Redis 分发；PG 通知保留为回退，双通道用事件 ID 去重。"""
from contextlib import asynccontextmanager, suppress
from collections import OrderedDict
import asyncio
import json
from uuid import uuid4
import asyncpg
from sqlalchemy import text
from src.core import config
from src.infrastructure.redis.client import connection, publish, RedisError
from .session import async_database_url


async def notify(db, channel, value):
    """PG 通知随事务提交，Redis 消息缓冲到同一事务提交之后发送。"""
    payload = json.dumps({**value, '_event_id': str(uuid4())})
    await db.execute(text('SELECT pg_notify(:channel, :payload)'), {'channel': channel, 'payload': payload})
    db.info.setdefault('redis_notifications', []).append((channel, payload))


async def publish_committed(messages):
    for channel, payload in messages:
        await publish(channel, payload)


@asynccontextmanager
async def listen(channel: str):
    """保留 PG 兜底；Redis 断开后重连，调用者收到原业务 JSON。"""
    queue = asyncio.Queue(maxsize=128)
    seen = OrderedDict()
    loop = asyncio.get_running_loop()
    delayed = set()

    def deliver(payload):
        try:
            value = json.loads(payload)
            event_id = value.pop('_event_id', None)
        except (ValueError, AttributeError):
            value, event_id = None, None
        if event_id:
            if event_id in seen:
                return
            seen[event_id] = None
            if len(seen) > 2048:
                seen.popitem(last=False)
            payload = json.dumps(value)
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(payload)

    redis_enabled = bool(config.REDIS_URL and config.REDIS_PUBSUB_ENABLED)

    def callback(_connection, _pid, _channel, payload):
        if not redis_enabled:
            deliver(payload)
            return
        # 给提交后的 Redis 分发留出短窗口；未送达时 PG 自动补上。
        handle = None
        def fallback():
            delayed.discard(handle)
            deliver(payload)
        handle = loop.call_later(0.15, fallback)
        delayed.add(handle)

    async def receive_redis(ready):
        while True:
            try:
                async with connection(subscription=True) as client:
                    async with client.pubsub() as subscriber:
                        await subscriber.subscribe(config.REDIS_PREFIX + ':events:' + channel)
                        ready.set()
                        async for message in subscriber.listen():
                            if message['type'] == 'message':
                                deliver(message['data'])
            except (RedisError, OSError):
                ready.set()  # Redis 不可用时不阻塞 PG 订阅的建立。
                await asyncio.sleep(1)

    url = async_database_url(config.DATABASE_URL).set(drivername='postgresql')
    pg = await asyncpg.connect(url.render_as_string(hide_password=False), timeout=10)
    receiver = None
    try:
        await pg.add_listener(channel, callback)
        if redis_enabled:
            ready = asyncio.Event()
            receiver = asyncio.create_task(receive_redis(ready))
            with suppress(TimeoutError):
                await asyncio.wait_for(ready.wait(), timeout=config.REDIS_TIMEOUT_SECONDS + 1)
        yield queue
    finally:
        for handle in delayed:
            handle.cancel()
        if receiver:
            receiver.cancel()
            with suppress(asyncio.CancelledError):
                await receiver
        await pg.close()
