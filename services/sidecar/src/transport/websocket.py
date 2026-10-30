"""会议 ASR WebSocket 命令入口。"""
import asyncio
import time
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..meetings.session import AsrSession
from ..providers.asr.doubao import DoubaoRecognizer, AsrProviderError
from .schemas import Start, control_message

router = APIRouter()


def allowed_origin(origin):
    """仅允许本机页面连接本地 Sidecar。"""
    if origin is None:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


@router.websocket("/ws")
async def asr_websocket(websocket: WebSocket):
    """分发控制消息和 PCM16 二进制音频。"""
    if not allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    session = None
    request = None
    send_lock = asyncio.Lock()
    active = websocket.app.state.asr_meetings

    async def send(message):
        async with send_lock:
            await websocket.send_json(message)

    async def error(code, message, request=None, retryable=False):
        payload = dict(type="asr.error", code=code, message=message, retryable=retryable)
        if request:
            payload.update(requestId=request.requestId, meetingId=request.meetingId)
        elif session:
            payload["meetingId"] = session.meeting_id
        await send(payload)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            audio = message.get("bytes")
            if audio is not None:
                if not session or session.failed or session.stop_event.is_set():
                    await error("INVALID_STATE", "请等待转写准备完成后再发送音频。")
                elif not audio or len(audio) % 2 or len(audio) > 64000:
                    await error("INVALID_AUDIO", "音频必须为 PCM16 小端数据，单帧不超过 64000 字节。")
                else:
                    await session.send_audio(audio)
                continue
            text = message.get("text", "")
            try:
                if len(text) > 16384:
                    raise ValueError("message too large")
                request = control_message.validate_json(text)
            except (ValidationError, ValueError):
                await error("INVALID_MESSAGE", "控制消息格式无效，请检查消息类型和音频参数。")
                continue
            if isinstance(request, Start):
                if session:
                    await error("ALREADY_STARTED", "当前连接已经启动转写。", request)
                    continue
                if request.meetingId in active:
                    await error("MEETING_BUSY", "该会议已有转写连接。", request, True)
                    continue
                override = None
                owner_id = None
                if request.ticket:
                    entry = websocket.app.state.asr_tickets.pop(request.ticket, None)
                    if not entry or entry[0] < time.monotonic() or entry[1] != request.meetingId:
                        await error("INVALID_TICKET", "转写连接凭证已失效，请重试。", request)
                        continue
                    owner_id = entry[2]
                    override = entry[3].asr() if entry[3] else None
                provider = DoubaoRecognizer(override) if override else DoubaoRecognizer()
                session = AsrSession(request.meetingId, send, provider, next_seq=request.nextSeq, offset_ms=request.offsetMs, owner_id=owner_id)
                active[request.meetingId] = session
                await session.prepare()
                await send(dict(type="asr.ready", requestId=request.requestId,
                                meetingId=request.meetingId, sessionId=session.session_id))
                session.task = asyncio.create_task(session.run())
            else:
                if not session or request.meetingId != session.meeting_id:
                    await error("INVALID_STATE", "会议尚未开始转写或会议标识不匹配。", request)
                    continue
                await session.stop()
                if session.failed:
                    await error("TRANSCRIPT_FAILED", "最后一批转写未能完成，请重试。", request, True)
                    continue
                await send(dict(type="asr.stopped", requestId=request.requestId,
                                meetingId=session.meeting_id, sessionId=session.session_id,
                                lastFinalSeq=session.last_final_seq))
                break
    except WebSocketDisconnect:
        pass
    except AsrProviderError as cause:
        try:
            await error(cause.code, str(cause), request, cause.retryable)
        except (RuntimeError, WebSocketDisconnect):
            pass
    except Exception:
        try:
            await error("INTERNAL_ERROR", "转写连接异常，请重新连接。", retryable=True)
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if session:
            await session.close()
            if active.get(session.meeting_id) is session:
                active.pop(session.meeting_id, None)
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass
