"""单次会议转写会话。"""
import asyncio
import logging

from starlette.websockets import WebSocketDisconnect
from uuid import uuid4

from . import repository
from ..providers.asr.doubao import AsrProviderError, DoubaoRecognizer


class AsrSession:
    def __init__(self, meeting_id, send, provider=None, *, next_seq=0, offset_ms=0):
        self.provider = provider or DoubaoRecognizer()
        self.meeting_id = meeting_id
        self.session_id = str(uuid4())
        self.send = send
        self.stop_event = asyncio.Event()
        self.task = None
        self.failed = False
        self.next_seq = next_seq
        self.offset = offset_ms
        self.last_final_seq = next_seq - 1
        self.segments = {}

    async def prepare(self):
        """启动上游识别，序号和时间基准由客户端从 API 恢复。"""
        await self.provider.open()

    async def run(self):
        """将识别事件转换为统一协议，确认片段交给前端调用 API 保存。"""
        try:
            async for event in self.provider.events():
                key = event["key"]
                content = {field: value for field, value in event.items() if field != "key"}
                content["startMs"] += self.offset
                content["endMs"] += self.offset
                previous = self.segments.get(key)
                if previous and (previous["isFinal"] or all(
                    previous[field] == value for field, value in content.items()
                )):
                    continue
                seq = previous["seq"] if previous else self.next_seq
                if not previous:
                    self.next_seq += 1
                segment = dict(content, id=f"{self.meeting_id}:{self.session_id}#{seq}", seq=seq,
                               revision=previous["revision"]+1 if previous else 1)
                if segment["isFinal"]:
                    self.last_final_seq = seq
                if not segment["isFinal"]:
                    await asyncio.to_thread(repository.save_temporary, self.meeting_id, self.session_id, segment)
                self.segments[key] = segment
                await self.send(dict(type="asr.transcript", meetingId=self.meeting_id,
                                     sessionId=self.session_id, segment=segment))
                if segment["isFinal"]:
                    try:
                        await asyncio.to_thread(repository.remove_temporary, self.meeting_id, self.session_id, seq)
                    except OSError:
                        logging.getLogger(__name__).warning("确认片段的临时文件清理失败")
        except asyncio.CancelledError:
            raise
        except Exception as cause:
            self.failed = True
            if isinstance(cause, AsrProviderError):
                logging.getLogger(__name__).warning("豆包转写失败，code=%s", cause.code)
            else:
                logging.getLogger(__name__).exception("会议转写任务失败")
            try:
                await self.send(dict(type="asr.error", meetingId=self.meeting_id,
                                     code=cause.code if isinstance(cause, AsrProviderError) else "TRANSCRIPT_FAILED",
                                     message=str(cause) if isinstance(cause, AsrProviderError) else "转写或临时文件写入失败，请重试。",
                                     retryable=cause.retryable if isinstance(cause, AsrProviderError) else True))
            except (RuntimeError, WebSocketDisconnect):
                pass

    async def stop(self):
        """等待最后的确认片段推送完成。"""
        self.stop_event.set()
        try:
            async with asyncio.timeout(8):
                await self.provider.finish()
                if self.task:
                    await asyncio.shield(self.task)
        except TimeoutError as cause:
            raise AsrProviderError("PROVIDER_STOP_TIMEOUT", "等待豆包最终结果超时，临时片段已保留。", True) from cause
        if not self.failed and any(not row["isFinal"] for row in self.segments.values()):
            raise AsrProviderError("FINAL_RESULT_MISSING", "部分文字尚未确认，已保留临时文件，请重试。", True)

    async def send_audio(self, audio):
        await self.provider.send_audio(audio)

    async def close(self):
        """释放识别任务。"""
        self.stop_event.set()
        if self.task:
            if not self.task.done():
                self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.provider.close()
