"""单次会议转写会话。"""
import asyncio
import logging

from starlette.websockets import WebSocketDisconnect
from uuid import uuid4

from . import repository, temporary
from ..providers.asr.mock import MockRecognizer
from ..providers.asr.doubao import AsrProviderError


class AsrSession:
    def __init__(self, meeting_id, send, provider=None):
        self.provider = provider or MockRecognizer()
        self.meeting_id = meeting_id
        self.session_id = str(uuid4())
        self.send = send
        self.stop_event = asyncio.Event()
        self.task = None
        self.failed = False
        self.audio_bytes = 0
        self.segments = {}

    async def prepare(self):
        """从持久化记录恢复序号和时间偏移。"""
        self.next_seq, self.offset = await asyncio.to_thread(repository.position, self.meeting_id)
        self.last_final_seq = self.next_seq-1
        await self.provider.open()

    async def sync_status(self):
        """推送本地待同步状态，不模拟云端同步成功。"""
        count = await asyncio.to_thread(repository.pending_count, self.meeting_id)
        await self.send(dict(type="asr.sync", meetingId=self.meeting_id,
                             pendingCount=count, status="pending" if count else "synced"))

    async def run(self):
        """将识别事件转换为统一协议，先落库再确认。"""
        try:
            async for event in self.provider.events():
                key = event.pop("key")
                previous = self.segments.get(key)
                if previous and previous["isFinal"]:
                    continue
                seq = previous["seq"] if previous else self.next_seq
                if not previous:
                    self.next_seq += 1
                segment = dict(event, id=f"{self.meeting_id}#{seq}", seq=seq,
                               revision=previous["revision"]+1 if previous else 1,
                               startMs=self.offset+event["startMs"], endMs=self.offset+event["endMs"])
                if segment["isFinal"]:
                    await asyncio.to_thread(repository.save_segment, self.meeting_id, segment)
                    self.last_final_seq = seq
                    try:
                        await asyncio.to_thread(temporary.remove_temporary, self.meeting_id, self.session_id, seq)
                    except OSError:
                        logging.getLogger(__name__).warning("已确认片段的临时文件清理失败")
                else:
                    await asyncio.to_thread(temporary.save_temporary, self.meeting_id, self.session_id, segment)
                self.segments[key] = segment
                await self.send(dict(type="asr.transcript", meetingId=self.meeting_id,
                                     sessionId=self.session_id, segment=segment))
                if segment["isFinal"]:
                    await self.sync_status()
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
                                     message=str(cause) if isinstance(cause, AsrProviderError) else "转写或本地保存失败，请重试。",
                                     retryable=cause.retryable if isinstance(cause, AsrProviderError) else True))
            except (RuntimeError, WebSocketDisconnect):
                pass

    async def stop(self):
        """等待最后的确认片段保存并推送完成。"""
        self.stop_event.set()
        await self.provider.finish()
        if self.task:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=8)
        if not self.failed and any(not row["isFinal"] for row in self.segments.values()):
            raise AsrProviderError("FINAL_RESULT_MISSING", "部分文字尚未确认，已保留临时文件，请重试。", True)
        await self.save_duration()

    async def send_audio(self, audio):
        await self.provider.send_audio(audio)
        self.audio_bytes += len(audio)

    async def save_duration(self):
        if self.audio_bytes:
            await asyncio.to_thread(repository.save_duration, self.meeting_id, self.session_id,
                                    self.offset, self.audio_bytes // 32)

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
        if hasattr(self, "offset"):
            await self.save_duration()
