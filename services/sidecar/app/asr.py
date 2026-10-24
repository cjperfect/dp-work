"""豆包流式 ASR 客户端（可选依赖：volcengine-python-sdk[streaming]）。

开启 show_utterances=True 获取分句信息：
- definite=false → 中间结果（前端更新当前行，不落库）
- definite=true  → 分句定型（落本地 SQLite，status=pending）

凭证经环境变量注入：VOLC_ACCESSKEY / VOLC_SECRETKEY / VOLC_APPID / VOLC_CLUSTER。
"""
from __future__ import annotations

import asyncio
import logging
import os

from . import store

log = logging.getLogger("sidecar.asr")

try:
    from volcenginesdkarkruntime import Ark  # type: ignore[import-not-found]
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


def sdk_available() -> bool:
    return _HAS_SDK


async def stream_mic(
    meeting_id: str,
    on_utterance,
    *,
    sample_rate: int = 16000,
    stop_event: asyncio.Event | None = None,
) -> None:
    """麦克风流式转写（开发调试入口）。

    on_utterance(utterance: dict) 每次收到豆包分句事件回调，utterance 含
    definite / text / speaker / start_ms / end_ms；definite=true 的已由本
    函数直接落库，回调用于前端推送。
    """
    if not _HAS_SDK:
        log.error("未安装 volcengine-python-sdk[streaming]，无法启动豆包 ASR")
        return
    raise NotImplementedError(
        "麦克风采集实现待接入（需 pyaudio 或音频文件源）。"
        "已就绪部分：definite 判定、落库、事件回调签名。"
    )


async def ingest_audio_chunk(
    meeting_id: str,
    pcm_bytes: bytes,
    on_utterance,
    seq_state: dict,
) -> None:
    """WebSocket 音频块入口：SDK 就绪后在此驱动 streaming 客户端。

    约定：utterance definite=true 时立即 store.save_segments 落库（pending），
    再把事件透传前端。
    """
    if not _HAS_SDK:
        log.warning("SDK 未安装，丢弃音频块 %d bytes", len(pcm_bytes))
        return
    raise NotImplementedError("豆包 streaming 客户端接入待实现（参考官方 WebSocket 示例）")
