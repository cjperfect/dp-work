"""使用本地 WebSocket 上游验证豆包二进制协议，不调用付费服务。"""
import asyncio
import gzip
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from src.providers.asr.doubao import DoubaoRecognizer, DoubaoSettings, AsrProviderError, parse_response
from src.meetings import repository
from src.meetings.session import AsrSession


def response(body, sequence=1, final=False, event=False):
    payload = gzip.compress(json.dumps(body).encode())
    flags = 1 | (2 if final else 0) | (4 if event else 0)
    return bytes([0x11, 0x90 | flags, 0x11, 0]) + struct.pack(">i", -sequence if final else sequence) + (struct.pack(">i", 1) if event else b"") + struct.pack(">I", len(payload)) + payload


def utterance(final):
    return {"result": {"utterances": [{"start_time": 0, "end_time": 160, "text": "讨论知识库。" if final else "讨论", "definite": final, "additions": {"speaker_id": "0"}}]}}


def decode_request(frame):
    sequence, size = struct.unpack_from(">iI", frame, 4)
    assert size == len(frame)-12
    return frame[1] >> 4, sequence, gzip.decompress(frame[12:])


class DoubaoProtocolTests(unittest.TestCase):
    def test_api_key_auth(self):
        self.assertEqual(DoubaoSettings(api_key="fixture-key").headers()["X-Api-Key"], "fixture-key")
        with self.assertRaises(AsrProviderError) as failure:
            DoubaoSettings().headers()
        self.assertEqual(failure.exception.code, "PROVIDER_AUTH_MISSING")

    def test_response_finality_uses_frame_flags_not_sentence_definite(self):
        body = utterance(True)
        self.assertEqual(parse_response(response(body)), (body, False))
        self.assertEqual(parse_response(response(body, final=True)), (body, True))
        self.assertEqual(parse_response(response(body, event=True)), (body, False))
        raw = json.dumps(body).encode()
        self.assertEqual(parse_response(bytes([0x11, 0x92, 0x10, 0])+struct.pack(">I", len(raw))+raw), (body, True))

    def test_malformed_and_provider_error_frames_have_safe_errors(self):
        invalid = [b"", b"short", response({})[:-1], bytes([0x11, 0x91, 0x11, 0])+struct.pack(">iI", 1, 4)+b"oops"]
        for frame in invalid:
            with self.assertRaises(AsrProviderError):
                parse_response(frame)
        raw = b"private upstream diagnostic"
        frame = bytes([0x11, 0xf0, 0x10, 0])+struct.pack(">II", 45000001, len(raw))+raw
        with self.assertRaises(AsrProviderError) as failure:
            parse_response(frame)
        self.assertNotIn("private upstream diagnostic", str(failure.exception))
        self.assertIn("45000001", str(failure.exception))


class DoubaoStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.db = Path(folder)/"dp.db"
        self.enterContext(patch.object(repository, "DB_PATH", self.db))
        self.enterContext(patch.object(repository, "TEMP_DIR", Path(folder)/"temp"))
        repository.init_db()

    async def create_provider(self, server):
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        def connector(endpoint, **kwargs):
            self.assertEqual(endpoint, "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
            return connect(url, **kwargs)
        return DoubaoRecognizer(DoubaoSettings(api_key="fixture-key"), connector)

    async def test_pcm_partial_final_persistence_and_negative_tail_frame(self):
        observed = {}
        async def upstream(socket):
            observed["key"] = socket.request.headers["X-Api-Key"]
            kind, seq, payload = decode_request(await socket.recv())
            observed["full"] = (kind, seq, json.loads(payload))
            await socket.send(response({}))
            kind, seq, payload = decode_request(await socket.recv())
            observed["audio"] = (kind, seq, payload)
            await socket.send(response(utterance(False), sequence=2))
            kind, seq, payload = decode_request(await socket.recv())
            observed["tail"] = (kind, seq, payload)
            # 确认一个分句不等于整个流结束。
            await socket.send(response(utterance(True), sequence=3))
            await socket.send(response(utterance(True), sequence=4, final=True))
        partial = asyncio.Event()
        messages = []
        async def send(message):
            messages.append(message)
            if message["type"] == "asr.transcript" and not message["segment"]["isFinal"]:
                partial.set()
        async with serve(upstream, "127.0.0.1", 0) as server:
            provider = await self.create_provider(server)
            session = AsrSession("meeting-1", send, provider)
            try:
                await session.prepare()
                session.task = asyncio.create_task(session.run())
                pcm = b"\x01\x00"*3200
                await session.send_audio(pcm)
                await asyncio.wait_for(partial.wait(), 2)
                self.assertEqual(repository.pending_count("meeting-1"), 0)
                self.assertTrue(repository.temporary_path("meeting-1", session.session_id).exists())
                await session.stop()
                finals = [m["segment"] for m in messages if m["type"] == "asr.transcript" and m["segment"]["isFinal"]]
                self.assertEqual(len(finals), 1)
                self.assertEqual(finals[0]["text"], "讨论知识库。")
                self.assertEqual(finals[0]["speakerId"], "speaker-1")
                self.assertEqual(repository.pending_count("meeting-1"), 1)
                self.assertFalse(repository.temporary_path("meeting-1", session.session_id).exists())
                self.assertEqual(repository.position("meeting-1"), (1, 200))
                self.assertEqual(observed["audio"], (2, 2, pcm))
                self.assertEqual(observed["tail"], (2, -3, b""))
                self.assertEqual(observed["full"][2]["audio"]["format"], "pcm")
                self.assertTrue(observed["full"][2]["request"]["enable_nonstream"])
                self.assertTrue(observed["full"][2]["request"]["show_utterances"])
            finally:
                await session.close()

    async def test_missing_final_sentence_preserves_temp_and_does_not_report_stopped(self):
        async def upstream(socket):
            await socket.recv()
            await socket.send(response({}))
            await socket.recv()
            await socket.send(response(utterance(False), sequence=2))
            await socket.recv()
            await socket.send(response({}, sequence=3, final=True))
        partial = asyncio.Event()
        async def send(message):
            if message["type"] == "asr.transcript":
                partial.set()
        async with serve(upstream, "127.0.0.1", 0) as server:
            session = AsrSession("meeting-1", send, await self.create_provider(server))
            try:
                await session.prepare()
                session.task = asyncio.create_task(session.run())
                await session.send_audio(bytes(6400))
                await asyncio.wait_for(partial.wait(), 2)
                with self.assertRaises(AsrProviderError) as failure:
                    await session.stop()
                self.assertEqual(failure.exception.code, "FINAL_RESULT_MISSING")
                self.assertEqual(repository.pending_count("meeting-1"), 0)
                self.assertTrue(repository.temporary_path("meeting-1", session.session_id).exists())
            finally:
                await session.close()

    async def test_startup_deadline_covers_waiting_for_first_response(self):
        async def blocked_receive():
            await asyncio.Future()
        socket = SimpleNamespace(response=SimpleNamespace(headers={}),
                                 send=AsyncMock(), recv=AsyncMock(side_effect=blocked_receive),
                                 close=AsyncMock())
        provider = DoubaoRecognizer(DoubaoSettings(api_key="fixture-key"), AsyncMock(return_value=socket))
        with patch("src.providers.asr.doubao.STARTUP_TIMEOUT", 0.02):
            with self.assertRaises(AsrProviderError) as failure:
                await asyncio.wait_for(provider.open(), 1)
        self.assertEqual(failure.exception.code, "PROVIDER_CONNECT_TIMEOUT")
        socket.close.assert_awaited_once()
        self.assertIsNone(provider.socket)

    async def test_cancelling_startup_closes_connection(self):
        receiving = asyncio.Event()
        async def blocked_receive():
            receiving.set()
            await asyncio.Future()
        socket = SimpleNamespace(response=SimpleNamespace(headers={}),
                                 send=AsyncMock(), recv=AsyncMock(side_effect=blocked_receive),
                                 close=AsyncMock())
        provider = DoubaoRecognizer(DoubaoSettings(api_key="fixture-key"), AsyncMock(return_value=socket))
        task = asyncio.create_task(provider.open())
        await asyncio.wait_for(receiving.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        socket.close.assert_awaited_once()
        self.assertIsNone(provider.socket)

    async def test_session_deduplicates_before_writing_with_resumed_time_offset(self):
        repository.save_duration("meeting-1", "previous-session", 0, 500)
        partial = dict(key=0, text="讨论", speakerId="speaker-1", startMs=0, endMs=160, isFinal=False)
        final = dict(partial, isFinal=True)
        async def events():
            for event in (partial, partial, final, final):
                yield event
        provider = SimpleNamespace(open=AsyncMock(), close=AsyncMock(), events=events)
        messages = []
        async def send(message):
            messages.append(message)
        session = AsrSession("meeting-1", send, provider)
        try:
            await session.prepare()
            with patch.object(repository, "save_temporary", wraps=repository.save_temporary) as temporary, \
                 patch.object(repository, "save_segment", wraps=repository.save_segment) as committed:
                await session.run()
            self.assertFalse(session.failed)
            self.assertEqual(temporary.call_count, 1)
            self.assertEqual(committed.call_count, 1)
            segments = [m["segment"] for m in messages if m["type"] == "asr.transcript"]
            self.assertEqual([s["revision"] for s in segments], [1, 2])
            self.assertEqual([(s["startMs"], s["endMs"]) for s in segments], [(500, 660)] * 2)
            self.assertTrue(segments[-1]["isFinal"])
            self.assertEqual(partial["startMs"], 0)
            self.assertEqual(partial["key"], 0)
            self.assertEqual(repository.pending_count("meeting-1"), 1)
        finally:
            await session.close()

    async def test_failed_handshake_reports_auth_error_without_echoing_credentials(self):
        async def rejected(_url, **kwargs):
            raise InvalidStatus(Response(401, "Unauthorized", Headers(), b"fixture-secret"))
        provider = DoubaoRecognizer(DoubaoSettings(api_key="fixture-secret"), rejected)
        with self.assertRaises(AsrProviderError) as failure:
            await provider.open()
        self.assertEqual(failure.exception.code, "PROVIDER_AUTH_FAILED")
        self.assertNotIn("fixture-secret", str(failure.exception))


    async def test_real_mode_route_forwards_pcm_and_returns_stopped_after_final_save(self):
        from fastapi.testclient import TestClient
        from src.main import app
        async def upstream(socket):
            await socket.recv()
            await socket.send(response({}))
            _, _, audio = decode_request(await socket.recv())
            self.assertEqual(len(audio), 6400)
            await socket.send(response(utterance(False), sequence=2))
            await socket.recv()
            await socket.send(response(utterance(True), sequence=3, final=True))
        async with serve(upstream, "127.0.0.1", 0) as server:
            url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            def factory():
                return DoubaoRecognizer(DoubaoSettings(api_key="fixture-key"), lambda _url, **kwargs: connect(url, **kwargs))
            def browser():
                with patch("src.transport.websocket.DoubaoRecognizer", side_effect=factory):
                    with TestClient(app) as client:
                        with client.websocket_connect("/ws") as ws:
                            ws.send_json(dict(type="asr.start", requestId="start", meetingId="meeting-1",
                                audio=dict(format="pcm",sampleRate=16000,channels=1,bitsPerSample=16)))
                            ready = ws.receive_json()
                            self.assertEqual(ready["requestId"], "start")
                            ws.send_bytes(bytes(6400))
                            while ws.receive_json()["type"] != "asr.transcript":
                                pass
                            ws.send_json(dict(type="asr.stop", requestId="stop", meetingId="meeting-1"))
                            final = None
                            while True:
                                event = ws.receive_json()
                                if event["type"] == "asr.transcript" and event["segment"]["isFinal"]:
                                    final = event["segment"]
                                if event["type"] == "asr.stopped":
                                    self.assertIsNotNone(final)
                                    self.assertEqual(event["lastFinalSeq"], final["seq"])
                                    break
            await asyncio.wait_for(asyncio.to_thread(browser), 5)
            self.assertEqual(repository.pending_count("meeting-1"), 1)
