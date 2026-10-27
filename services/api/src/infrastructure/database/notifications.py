"""PostgreSQL 跨进程状态通知。"""
from contextlib import asynccontextmanager
import asyncio
import asyncpg
from src.core import config
from .session import async_database_url


@asynccontextmanager
async def listen(channel: str):
    """订阅通知，退出时释放专用连接。"""
    queue = asyncio.Queue(maxsize=128)
    url = async_database_url(config.DATABASE_URL).set(drivername="postgresql")
    connection = await asyncpg.connect(url.render_as_string(hide_password=False), timeout=10)
    def callback(_connection, _pid, _channel, payload):
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(payload)
    try:
        await connection.add_listener(channel, callback)
        yield queue
    finally:
        await connection.close()
