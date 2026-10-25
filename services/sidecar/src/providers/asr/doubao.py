"""豆包双向流式 ASR WebSocket 适配。"""
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
import gzip
from io import BytesIO
import json
import logging
import struct
from typing import Any, TypedDict
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus, ConnectionClosed

from ... import config

log = logging.getLogger(__name__)
MAX_PAYLOAD = 4 * 1024 * 1024
STARTUP_TIMEOUT = 8
SEND_TIMEOUT = 3
CLOSE_TIMEOUT = 2
PROTOCOL_VERSION = 1
HEADER_WORDS = 1
WORD_BYTES = 4
FULL_REQUEST = 1
AUDIO_REQUEST = 2
FULL_RESPONSE = 9
ERROR_RESPONSE = 15
FLAG_SEQUENCE = 1
FLAG_FINAL = 2
FLAG_EVENT = 4
SERIALIZATION_JSON = 1
COMPRESSION_GZIP = 1
ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"


class TranscriptEvent(TypedDict):
    key: int
    text: str
    speakerId: str | None
    startMs: int
    endMs: int
    isFinal: bool


class AsrProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class DoubaoSettings:
    api_key: str = ""
    resource_id: str = "volc.seedasr.sauc.duration"
    speaker_info: bool = True

    @classmethod
    def from_config(cls) -> "DoubaoSettings":
        return cls(api_key=config.VOLC_API_KEY, resource_id=config.VOLC_RESOURCE_ID,
                   speaker_info=config.VOLC_SPEAKER_INFO)

    def headers(self) -> dict[str, str]:
        """构造仅用于上游握手的鉴权头。"""
        if not self.resource_id:
            raise AsrProviderError("PROVIDER_CONFIG_ERROR", "请配置豆包语音资源 ID。")
        if not self.api_key:
            raise AsrProviderError("PROVIDER_AUTH_MISSING", "请在 Sidecar .env 中配置 VOLC_API_KEY。")
        request_id = str(uuid4())
        return {"X-Api-Key": self.api_key, "X-Api-Resource-Id": self.resource_id,
                "X-Api-Request-Id": request_id, "X-Api-Connect-Id": request_id, "X-Api-Sequence": "-1"}

    def payload(self) -> dict[str, Any]:
        """构造音频格式与识别参数。"""
        request: dict[str, Any] = {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True,
                   "enable_nonstream": True, "show_utterances": True, "result_type": "full"}
        if self.speaker_info:
            request["enable_speaker_info"] = True
            if "seedasr" in self.resource_id:
                request["ssd_version"] = "200"
        return {"user": {"uid": "dp-work"},
                   "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
                   "request": request}


def request_frame(message_type: int, payload: bytes, sequence: int, *,
                  final: bool = False, serialized: bool = False) -> bytes:
    """编码豆包协议的序号、压缩载荷和结束标记。"""
    compressed = gzip.compress(payload)
    flags = FLAG_SEQUENCE | (FLAG_FINAL if final else 0)
    serialization = SERIALIZATION_JSON if serialized else 0
    header = bytes([(PROTOCOL_VERSION << 4) | HEADER_WORDS, (message_type << 4) | flags,
                    (serialization << 4) | COMPRESSION_GZIP, 0])
    return header + struct.pack(">iI", -sequence if final else sequence, len(compressed)) + compressed


def parse_response(frame: bytes | str) -> tuple[dict[str, Any], bool]:
    """解码响应；协议尾帧与分句确认分别处理。"""
    try:
        if not isinstance(frame, bytes) or len(frame) < 8 or frame[0] >> 4 != PROTOCOL_VERSION:
            raise ValueError("header")
        cursor = (frame[0] & 15) * WORD_BYTES
        kind, flags = frame[1] >> 4, frame[1] & 15
        serialization, compression = frame[2] >> 4, frame[2] & 15
        if cursor < 4 or cursor > len(frame) or kind not in (FULL_RESPONSE, ERROR_RESPONSE):
            raise ValueError("header")

        def integer(signed: bool = False) -> int:
            nonlocal cursor
            value = struct.unpack_from(">i" if signed else ">I", frame, cursor)[0]
            cursor += WORD_BYTES
            return value

        sequence = integer(True) if flags & FLAG_SEQUENCE else 0
        if flags & FLAG_EVENT:
            integer(True)
        code = integer() if kind == ERROR_RESPONSE else 0
        size = integer()
        if size > MAX_PAYLOAD or cursor + size != len(frame):
            raise ValueError("payload length")
        payload = frame[cursor:]
        if compression == COMPRESSION_GZIP:
            with gzip.GzipFile(fileobj=BytesIO(payload)) as stream:
                payload = stream.read(MAX_PAYLOAD + 1)
        elif compression != 0:
            raise ValueError("compression")
        if len(payload) > MAX_PAYLOAD:
            raise ValueError("payload limit")
        if kind == ERROR_RESPONSE:
            raise AsrProviderError("PROVIDER_REJECTED", f"豆包识别请求失败（错误码 {code}）。", True)
        if serialization != SERIALIZATION_JSON:
            raise ValueError("serialization")
        body = json.loads(payload) if payload else {}
        if not isinstance(body, dict):
            raise ValueError("payload")
    except (ValueError, OSError, EOFError, struct.error) as cause:
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包响应格式无效或数据不完整。", True) from cause
    if body.get("code", 0) not in (0, 20000000):
        raise AsrProviderError("PROVIDER_REJECTED", f"豆包识别请求失败（错误码 {body['code']}）。", True)
    return body, bool(flags & FLAG_FINAL) or sequence < 0


class DoubaoRecognizer:
    def __init__(self, settings: DoubaoSettings | None = None,
                 connector: Callable[..., Awaitable[ClientConnection]] | None = None) -> None:
        self.settings = settings or DoubaoSettings.from_config()
        self.connector = connector or connect
        self.socket: ClientConnection | None = None
        self.sequence = 1
        self.finished = False
        self.stopping = False
        self.initial: dict[str, Any] | None = None
        self.send_lock = asyncio.Lock()

    async def open(self) -> None:
        """等待鉴权与参数确认后，允许前端发送音频。"""
        headers = self.settings.headers()
        try:
            async with asyncio.timeout(STARTUP_TIMEOUT):
                self.socket = await self.connector(ASR_URL, additional_headers=headers,
                    open_timeout=STARTUP_TIMEOUT, close_timeout=CLOSE_TIMEOUT, max_size=MAX_PAYLOAD, max_queue=8,
                    compression=None, proxy=None)
                log_id = self.socket.response.headers.get("X-Tt-Logid")
                if log_id:
                    log.info("豆包 ASR 已连接，logid=%s", log_id)
                await self._send(json.dumps(self.settings.payload()).encode(), audio=False)
                frame = await self.socket.recv()
                self.initial, self.finished = parse_response(frame)
                if self.finished:
                    raise AsrProviderError("PROVIDER_REJECTED", "豆包识别会话在开始时已结束，请检查配置。", True)
        except asyncio.CancelledError:
            await self.close()
            raise
        except TimeoutError as cause:
            await self.close()
            raise AsrProviderError("PROVIDER_CONNECT_TIMEOUT", "连接豆包语音服务超时，请重试。", True) from cause
        except Exception as cause:
            await self.close()
            if isinstance(cause, AsrProviderError):
                raise
            if isinstance(cause, InvalidStatus):
                status = cause.response.status_code
                unauthorized = status in (401, 403)
                raise AsrProviderError(
                    "PROVIDER_AUTH_FAILED" if unauthorized else "PROVIDER_CONNECT_FAILED",
                    f"豆包连接被拒绝（HTTP {status}），请检查凭证、资源 ID 和服务开通状态。",
                    not unauthorized,
                ) from None
            raise AsrProviderError("PROVIDER_CONNECT_FAILED", "无法连接豆包语音服务，请检查网络后重试。", True) from cause

    async def _send(self, payload: bytes, *, audio: bool = True, final: bool = False) -> None:
        """统一发送数据帧，串行维护包序号。"""
        async with self.send_lock:
            frame = request_frame(AUDIO_REQUEST if audio else FULL_REQUEST, payload, self.sequence,
                                  final=final, serialized=not audio)
            try:
                await asyncio.wait_for(self.socket.send(frame), SEND_TIMEOUT)
                self.sequence += 1
            except Exception as cause:
                raise AsrProviderError("PROVIDER_SEND_FAILED", "向豆包发送数据失败，请重试。", True) from cause

    async def send_audio(self, audio: bytes) -> None:
        """发送 PCM 音频。"""
        if not self.socket or self.stopping or self.finished:
            raise AsrProviderError("PROVIDER_SESSION_CLOSED", "豆包转写会话已结束，请重新开始。", True)
        await self._send(audio)

    async def finish(self) -> None:
        """发送尾帧，接收任务继续等待最终结果。"""
        if self.socket and not self.stopping and not self.finished:
            self.stopping = True
            await self._send(b"", final=True)

    def normalize(self, body: dict[str, Any]) -> Iterator[TranscriptEvent]:
        """将豆包分句转换为统一字段。"""
        result = body.get("result", {})
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return
        utterances = result.get("utterances", [])
        if not isinstance(utterances, list):
            return
        for index, row in enumerate(utterances):
            if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"]:
                continue
            start, end = row.get("start_time"), row.get("end_time")
            if type(start) is not int or type(end) is not int or start < 0 or end < start:
                continue
            additions = row.get("additions", {})
            if isinstance(additions, str):
                try:
                    additions = json.loads(additions)
                except ValueError:
                    additions = {}
            speaker = (additions.get("speaker_id") if isinstance(additions, dict) else None)
            if speaker is None:
                speaker = row.get("speaker_id")
            speaker_id = None if speaker is None else str(speaker)
            if speaker_id is not None and speaker_id.isdigit():
                speaker_id = f"speaker-{int(speaker_id)+1}"
            yield TranscriptEvent(key=index, text=row["text"], speakerId=speaker_id,
                                  startMs=start, endMs=end, isFinal=row.get("definite") is True)

    async def events(self) -> AsyncIterator[TranscriptEvent]:
        """连续返回分句；只有协议尾帧才代表流结束。"""
        body = self.initial or {}
        try:
            while True:
                for event in self.normalize(body):
                    yield event
                if self.finished:
                    if not self.stopping:
                        raise AsrProviderError("PROVIDER_SESSION_ENDED", "豆包识别会话已结束，请重新开始转写。", True)
                    return
                body, self.finished = parse_response(await self.socket.recv())
        except (ConnectionClosed, OSError) as cause:
            raise AsrProviderError("PROVIDER_DISCONNECTED", "豆包转写连接中断，请重新开始。", True) from cause

    async def close(self) -> None:
        """释放豆包连接，不影响已保存的片段。"""
        socket, self.socket = self.socket, None
        if socket:
            await socket.close()
