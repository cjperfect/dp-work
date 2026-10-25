"""模拟 ASR 分句流（真豆包 SDK 接入前用于打通 Web ⇄ Sidecar 消息链路）。

行为：asr.start 后按固定节奏广播 utterance——
先 definite=false（中间结果，前端更新待定行），再 definite=true（定型，前端落库）。
"""
from __future__ import annotations

import asyncio
import time

# (发言人, 分句文本)：一轮模拟会议的发言内容
MOCK_SENTENCES: list[tuple[str, str]] = [
    ("王明", "对齐 RAG 召回优化方案"),
    ("李静", "评估集口径保持一致"),
    ("陈工", "pgvector 检索链路今晚联调"),
    ("王明", "召回率从 0.57 提升到 0.70"),
    ("李静", "本周五前给出结论"),
]


async def mock_asr(ws, meeting_id: str, stop_event: asyncio.Event, start_ms: int) -> None:
    """向单个 ws 连接广播模拟分句流，stop_event 置位时停止。"""
    seq = 0
    t0 = time.time() * 1000
    try:
        for speaker, text in MOCK_SENTENCES:
            if stop_event.is_set():
                break
            # 中间结果流：按 4 字符步进模拟 ASR 渐显
            for i in range(1, len(text) + 1, 4):
                if stop_event.is_set():
                    break
                await ws.send_json(
                    {
                        "type": "utterance",
                        "definite": False,
                        "text": text[:i],
                        "speaker": speaker,
                    }
                )
                await asyncio.sleep(0.25)
            # 定型
            await ws.send_json(
                {
                    "type": "utterance",
                    "definite": True,
                    "seq": seq,
                    "text": text,
                    "speaker": speaker,
                    "start_ms": int(time.time() * 1000 - t0),
                    "end_ms": int(time.time() * 1000 - t0) + 250,
                }
            )
            seq += 1
            await asyncio.sleep(1.0)
    except Exception:  # noqa: BLE001 连接断开即退出
        return
