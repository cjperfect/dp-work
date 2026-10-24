"""定时批量上行：取本地 pending 分句 → POST api /segments → 标记 synced。

失败保留 pending，下个周期重试（attempt +1）；网络恢复/会议结束时可手动触发 flush。
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

from . import store

log = logging.getLogger("sidecar.sync")

API_BASE = os.environ.get("SYNC_API_BASE", "http://localhost:8000").rstrip("/")
INTERVAL = float(os.environ.get("SYNC_INTERVAL_SEC", "5"))
BATCH_SIZE = int(os.environ.get("SYNC_BATCH_SIZE", "200"))


def _sync_once(meeting_id: str) -> None:
    """单次批量上行（同步阻塞实现，由 async 包装调用）。"""
    pending = store.pending_segments(meeting_id, limit=BATCH_SIZE)
    if not pending:
        return
    payload = {
        "meeting_id": meeting_id,
        "segments": [
            {
                "id": p["id"],
                "seq": p["seq"],
                "speaker": p["speaker"],
                "text": p["text"],
                "start_ms": p["start_ms"],
                "end_ms": p["end_ms"],
            }
            for p in pending
        ],
    }
    try:
        resp = httpx.post(f"{API_BASE}/api/v1/segments", json=payload, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("上行失败（保留 pending，下次重试）: %s", e)
        return
    data = resp.json()
    written = data.get("written", 0)
    if written:
        store.mark_synced(meeting_id, [p["id"] for p in pending[:written]])
        log.info("已同步 %d 条分句（meeting=%s）", written, meeting_id)


async def sync_loop(meeting_ids: "Callable[[], list[str]]") -> None:
    """后台循环：每 INTERVAL 秒对活跃会议各做一次批量上行。"""
    while True:
        try:
            for meeting_id in meeting_ids():
                await asyncio.to_thread(_sync_once, meeting_id)
        except Exception:  # noqa: BLE001 单次失败不影响循环
            log.exception("sync loop 异常")
        await asyncio.sleep(INTERVAL)


async def flush(meeting_id: str) -> None:
    """会议结束/前端主动触发时立即清空 pending 队列。"""
    for _ in range(50):  # 最多 50 批（防极端积压）
        pending = store.pending_segments(meeting_id, limit=BATCH_SIZE)
        if not pending:
            break
        await asyncio.to_thread(_sync_once, meeting_id)
