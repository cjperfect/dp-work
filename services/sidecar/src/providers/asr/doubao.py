"""豆包双向流式 ASR WebSocket 适配。"""
import asyncio
from dataclasses import dataclass
import gzip
from io import BytesIO
import json
import logging
import struct
from urllib.parse import urlparse
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, ConnectionClosed

from ... import config

log = logging.getLogger(__name__)
MAX_PAYLOAD = 4 * 1024 * 1024


class AsrProviderError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class DoubaoSettings:
    api_key: str = ""
    app_id: str = ""
    access_token: str = ""
    resource_id: str = "volc.seedasr.sauc.duration"
    url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    speaker_info: bool = True

    @classmethod
    def from_config(cls):
        return cls(api_key=config.VOLC_API_KEY, app_id=config.VOLC_APPID,
                   access_token=config.VOLC_ACCESS_TOKEN, resource_id=config.VOLC_RESOURCE_ID,
                   url=config.VOLC_ASR_URL, speaker_info=config.VOLC_SPEAKER_INFO)

    def headers(self):
        """构造仅用于上游握手的鉴权头。"""
        parsed = urlparse(self.url)
        if (parsed.scheme != "wss" or parsed.hostname != "openspeech.bytedance.com"
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"/api/v3/sauc/bigmodel_async", "/api/v3/plan/sauc/bigmodel_async"}):
            raise AsrProviderError("PROVIDER_CONFIG_ERROR", "豆包 ASR 地址配置无效，请检查 VOLC_ASR_URL。")
        if not self.resource_id:
            raise AsrProviderError("PROVIDER_CONFIG_ERROR", "请配置豆包语音资源 ID。")
        request_id = str(uuid4())
        headers = {"X-Api-Resource-Id": self.resource_id, "X-Api-Request-Id": request_id,
                   "X-Api-Connect-Id": request_id, "X-Api-Sequence": "-1"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        elif self.app_id and self.access_token:
            headers.update({"X-Api-App-Key": self.app_id, "X-Api-Access-Key": self.access_token})
        else:
            raise AsrProviderError("PROVIDER_AUTH_MISSING", "请在 Sidecar .env 中配置 VOLC_API_KEY，或 VOLC_APPID 与 VOLC_ACCESS_TOKEN。")
        return headers


def request_frame(message_type, payload, sequence, *, final=False, serialized=False):
    """编码豆包协议的序号、压缩载荷和结束标记。"""
    compressed = gzip.compress(payload)
    flags = 3 if final else 1
    header = bytes([0x11, (message_type << 4) | flags, (0x10 if serialized else 0) | 1, 0])
    return header + struct.pack(">iI", -sequence if final else sequence, len(compressed)) + compressed


def parse_response(frame):
    """解码上游响应；流结束依据帧标记，不依据分句 definite。"""
    if not isinstance(frame, bytes) or len(frame) < 8 or frame[0] >> 4 != 1:
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包返回了无效的协议数据。", True)
    header_size = (frame[0] & 15) * 4
    kind, flags = frame[1] >> 4, frame[1] & 15
    serialization, compression = frame[2] >> 4, frame[2] & 15
    cursor = header_size

    def integer(signed=False):
        nonlocal cursor
        if cursor + 4 > len(frame):
            raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包响应数据不完整。", True)
        value = struct.unpack_from(">i" if signed else ">I", frame, cursor)[0]
        cursor += 4
        return value

    if header_size < 4 or header_size > len(frame):
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包响应头无效。", True)
    sequence = integer(True) if flags & 1 else 0
    if flags & 4:
        integer(True)
    code = integer() if kind == 15 else 0
    if kind not in (9, 15):
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包返回了不支持的消息类型。", True)
    size = integer()
    if size > MAX_PAYLOAD or cursor + size != len(frame):
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包响应长度无效。", True)
    payload = frame[cursor:]
    try:
        if compression == 1:
            with gzip.GzipFile(fileobj=BytesIO(payload)) as stream:
                payload = stream.read(MAX_PAYLOAD + 1)
        elif compression != 0:
            raise ValueError("compression")
        if len(payload) > MAX_PAYLOAD:
            raise ValueError("payload limit")
        if kind == 15:
            raise AsrProviderError("PROVIDER_REJECTED", f"豆包识别请求失败（错误码 {code}），请检查资源配置和音频格式。", True)
        if serialization != 1:
            raise ValueError("serialization")
        body = json.loads(payload) if payload else {}
        if not isinstance(body, dict):
            raise ValueError("payload")
    except (ValueError, OSError, EOFError) as cause:
        raise AsrProviderError("PROVIDER_PROTOCOL_ERROR", "豆包响应解析失败。", True) from cause
    business_code = body.get("code", 0)
    if business_code not in (0, 20000000):
        raise AsrProviderError("PROVIDER_REJECTED", f"豆包识别请求失败（错误码 {business_code}）。", True)
    return body, bool(flags & 2) or sequence < 0


class DoubaoRecognizer:
    mode = "doubao"

    def __init__(self, settings=None, connector=None):
        self.settings = settings or DoubaoSettings.from_config()
        self.connector = connector or connect
        self.socket = None
        self.sequence = 1
        self.finished = False
        self.stopping = False
        self.initial = None
        self.seen = {}
        self.send_lock = asyncio.Lock()

    async def open(self):
        """等待鉴权与参数确认后，允许前端发送音频。"""
        headers = self.settings.headers()
        try:
            self.socket = await self.connector(self.settings.url, additional_headers=headers,
                open_timeout=6, close_timeout=2, max_size=MAX_PAYLOAD, max_queue=8,
                compression=None, proxy=None)
            log_id = self.socket.response.headers.get("X-Tt-Logid")
            if log_id:
                log.info("豆包 ASR 已连接，logid=%s", log_id)
            request = {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True,
                       "enable_nonstream": True, "show_utterances": True, "result_type": "full"}
            if self.settings.speaker_info:
                request["enable_speaker_info"] = True
                if "seedasr" in self.settings.resource_id:
                    request["ssd_version"] = "200"
            payload = {"user": {"uid": "dp-work"},
                       "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
                       "request": request}
            await asyncio.wait_for(self.socket.send(request_frame(1, json.dumps(payload).encode(), self.sequence, serialized=True)), 3)
            self.sequence += 1
            frame = await asyncio.wait_for(self.socket.recv(), 6)
            self.initial, self.finished = parse_response(frame)
            if self.finished:
                raise AsrProviderError("PROVIDER_REJECTED", "豆包识别会话在开始时已结束，请检查配置。", True)
        except InvalidStatus as cause:
            await self.close()
            status = cause.response.status_code
            code = "PROVIDER_AUTH_FAILED" if status in (401, 403) else "PROVIDER_CONNECT_FAILED"
            raise AsrProviderError(code, f"豆包连接被拒绝（HTTP {status}），请检查凭证、资源 ID 和服务开通状态。", status not in (401, 403)) from None
        except AsrProviderError:
            await self.close()
            raise
        except Exception as cause:
            await self.close()
            raise AsrProviderError("PROVIDER_CONNECT_FAILED", "无法连接豆包语音服务，请检查网络后重试。", True) from cause

    async def send_audio(self, audio):
        """按收到的顺序发送 PCM 音频，发送受阻时停止而不丢帧。"""
        if not self.socket or self.stopping or self.finished:
            raise AsrProviderError("PROVIDER_SESSION_CLOSED", "豆包转写会话已结束，请重新开始。", True)
        async with self.send_lock:
            try:
                await asyncio.wait_for(self.socket.send(request_frame(2, audio, self.sequence)), 3)
                self.sequence += 1
            except Exception as cause:
                raise AsrProviderError("PROVIDER_SEND_FAILED", "音频发送失败，请重新开始转写。", True) from cause

    async def finish(self):
        """发送负序号尾帧，接收任务继续等待最终响应。"""
        if not self.socket or self.stopping or self.finished:
            return
        self.stopping = True
        async with self.send_lock:
            try:
                await asyncio.wait_for(self.socket.send(request_frame(2, b"", self.sequence, final=True)), 3)
            except Exception as cause:
                raise AsrProviderError("PROVIDER_SEND_FAILED", "无法提交最后的音频，请重试。", True) from cause

    def normalize(self, body):
        """统一分句字段，并去除全量结果中的重复确认片段。"""
        result = body.get("result", {})
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            return
        for index, row in enumerate(result.get("utterances", [])):
            if not isinstance(row, dict) or not row.get("text"):
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
            event = dict(key=index, text=row["text"], speakerId=str(speaker) if speaker is not None else None,
                         startMs=start, endMs=end, isFinal=row.get("definite") is True)
            old = self.seen.get(index)
            if old and (old["isFinal"] or old == event):
                continue
            self.seen[index] = event
            yield event.copy()

    async def events(self):
        """连续接收增量文本，只有协议尾帧才代表流结束。"""
        if self.initial:
            for event in self.normalize(self.initial):
                yield event
        try:
            while not self.finished:
                frame = await self.socket.recv()
                body, self.finished = parse_response(frame)
                for event in self.normalize(body):
                    yield event
        except AsrProviderError:
            raise
        except (ConnectionClosed, OSError) as cause:
            raise AsrProviderError("PROVIDER_DISCONNECTED", "豆包转写连接中断，请重新开始。", True) from cause
        if not self.stopping:
            raise AsrProviderError("PROVIDER_SESSION_ENDED", "豆包识别会话已结束，请重新开始转写。", True)

    async def close(self):
        """释放豆包连接，不影响已保存的片段。"""
        socket, self.socket = self.socket, None
        if socket:
            await socket.close()
