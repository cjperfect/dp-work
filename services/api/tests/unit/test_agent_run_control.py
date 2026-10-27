"""取消与建连同时完成时也须释放已经打开的上游连接。"""
import asyncio
import pytest
from src.modules.agents.run_control import RunControl, RunStopped


def test_cancel_connection_completion_race_closes_upstream():
    class Upstream:
        closed = False
        async def close(self):
            self.closed = True
    async def case():
        control, upstream = RunControl('fixture'), Upstream()
        control.stopped.set()
        control.stop_waiter = asyncio.create_task(control.stopped.wait())
        async def connect():
            return upstream
        try:
            with pytest.raises(RunStopped):
                await control.wait(connect())
            assert upstream.closed
        finally:
            await control.close()
    asyncio.run(case())
