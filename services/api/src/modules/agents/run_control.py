"""通过 PG 通知停止执行连接，兼容多个 API 进程。"""
import asyncio
import json
from contextlib import suppress
from src.infrastructure.database import session
from src.infrastructure.database.notifications import listen
from .run_models import AgentRun
from . import run_service


class RunStopped(Exception):
    """当前运行已取消、失效或被回收。"""


class RunControl:
    """订阅先于状态检查，网络等待不持有数据库事务。"""
    def __init__(self, run_id):
        self.run_id, self.status = run_id, "running"
        self.subscription = listen("agent_runs")
        self.stopped = asyncio.Event()
        self.monitor = self.stop_waiter = None
        self.entered = False

    async def open(self):
        """连接通知通道并启动有界的状态检查。"""
        try:
            self.queue = await self.subscription.__aenter__()
            self.entered = True
            await self.check()
            self.monitor = asyncio.create_task(self.watch())
            self.stop_waiter = asyncio.create_task(self.stopped.wait())
            return self
        except BaseException:
            await self.close()
            raise

    async def check(self):
        """通知以 PG 状态为准，超过期限时先收敛运行。"""
        await run_service.recover(self.run_id)
        async with session.read_session() as db:
            row = await db.get(AgentRun, self.run_id)
        if row is None or row.status != "running":
            self.status = row.status if row else "interrupted"
            self.stopped.set()

    async def watch(self):
        """通知即时响应，五秒检查覆盖通知丢失和执行超时。"""
        try:
            while not self.stopped.is_set():
                try:
                    payload = await asyncio.wait_for(self.queue.get(), timeout=5)
                    if json.loads(payload).get("run_id") != self.run_id:
                        continue
                except TimeoutError:
                    pass
                await self.check()
        except Exception:
            self.status = "interrupted"
            self.stopped.set()

    async def wait(self, operation):
        """运行停止时取消正在等待的连接或流读取。"""
        task = asyncio.ensure_future(operation)
        delivered = False
        try:
            await asyncio.wait((task, self.stop_waiter), return_when=asyncio.FIRST_COMPLETED)
            if self.stopped.is_set():
                raise RunStopped()
            result = await task
            delivered = True
            return result
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                result = await task
                if not delivered and hasattr(result, "close"):
                    await result.close()

    async def close(self):
        """释放监听和后台检查任务。"""
        for task in (self.monitor, self.stop_waiter):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        self.monitor = self.stop_waiter = None
        if self.entered:
            self.entered = False
            await self.subscription.__aexit__(None, None, None)
