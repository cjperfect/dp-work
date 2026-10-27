"""统一单次执行的事件身份和结束边界。"""
import asyncio
import time
from uuid import uuid4


async def run_events(events, run_id=None, model=None):
    """贯穿同一 run_id，确保只发布一个终态并关闭底层迭代器。"""
    run_id = run_id or str(uuid4())
    started = time.monotonic()
    try:
        yield {"type": "start", "run_id": run_id, "status": "running", "model": model}
        async for event in events:
            kind = event.get("type")
            if kind == "start":
                continue
            event = {**event, "run_id": run_id}
            if kind == "approval":
                event["status"] = "waiting_approval"
                yield event
                return
            if kind in ("done", "error"):
                event["status"] = "completed" if kind == "done" else "failed"
                event["duration_ms"] = round((time.monotonic() - started) * 1000)
                yield event
                return
            yield event
        yield {"type": "error", "run_id": run_id, "status": "interrupted", "code": "AGENT_DISCONNECTED",
               "message": "执行提前中断，请重试。"}
    except asyncio.CancelledError:
        raise
    finally:
        await events.aclose()
