"""ASR 协议、SQLite 提交顺序和连接生命周期测试。"""
from contextlib import closing
import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.main import app
from src.meetings import repository

STEP_SECONDS = 0.01


class TestRecognizer:
    """测试替身，不作为应用的识别模式发布。"""
    def __init__(self):
        self.stopped = asyncio.Event()

    async def open(self):
        pass

    async def send_audio(self, audio):
        pass

    async def finish(self):
        self.stopped.set()

    async def close(self):
        self.stopped.set()

    async def events(self):
        yield dict(key=0, text="测试转写", speakerId="speaker-1", startMs=0, endMs=10, isFinal=False)
        try:
            await asyncio.wait_for(self.stopped.wait(), STEP_SECONDS)
        except TimeoutError:
            pass
        yield dict(key=0, text="测试转写", speakerId="speaker-1", startMs=0, endMs=20, isFinal=True)


AUDIO = dict(format="pcm", sampleRate=16000, channels=1, bitsPerSample=16)


def start(meeting="meeting-1", request="start-1", **changes):
    return dict(type="asr.start", requestId=request, meetingId=meeting, audio=AUDIO, **changes)


def until(ws, kind):
    messages = []
    for _ in range(100):
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == kind:
            return message, messages
    raise AssertionError(f"没有收到 {kind}")


class AsrWebSocketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / "dp.db"
        for target, value in [
            ("src.meetings.repository.DB_PATH", self.db),
            ("src.meetings.repository.TEMP_DIR", Path(self.temporary.name) / "temp"),
        ]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.enterContext(patch("src.transport.websocket.DoubaoRecognizer", side_effect=TestRecognizer))
        self.client = self.enterContext(TestClient(app))

    @patch(f"{__name__}.STEP_SECONDS", 1)
    def test_final_is_committed_before_emission_and_stop_drains_the_current_segment(self):
        with self.client.websocket_connect("/ws", headers={"origin": "http://localhost:3000"}) as ws:
            ws.send_json(start())
            ready = ws.receive_json()
            self.assertEqual(ready["type"], "asr.ready")
            self.assertEqual(ready["requestId"], "start-1")
            self.assertNotIn("mode", ready)
            partial, _ = until(ws, "asr.transcript")
            self.assertFalse(partial["segment"]["isFinal"])
            temporary = Path(self.temporary.name) / "temp/asr/meeting-1" / ready["sessionId"] / "0.json"
            self.assertEqual(json.loads(temporary.read_text())["segment"], partial["segment"])
            self.assertEqual(repository.pending_count("meeting-1"), 0)
            ws.send_bytes(bytes(6400))
            ws.send_json(dict(type="asr.stop", requestId="stop-1", meetingId="meeting-1"))
            stopped, messages = until(ws, "asr.stopped")
            finals = [m for m in messages if m["type"] == "asr.transcript" and m["segment"]["isFinal"]]
            self.assertEqual(len(finals), 1)
            final = finals[0]["segment"]
            self.assertEqual(final["id"], partial["segment"]["id"])
            self.assertGreater(final["revision"], partial["segment"]["revision"])
            with closing(sqlite3.connect(self.db)) as conn:
                row = conn.execute("SELECT text,sync_status FROM transcript_segments WHERE id=?", (final["id"],)).fetchone()
            self.assertEqual(row, (final["text"], "pending"))
            self.assertFalse(temporary.exists())
            self.assertEqual(stopped["lastFinalSeq"], final["seq"])
            self.assertEqual(stopped["requestId"], "stop-1")
            self.assertTrue(any(m["type"] == "asr.sync" and m["status"] == "pending" for m in messages))

    def test_reconnect_continues_sequence_and_recording_time(self):
        segments = []
        sessions = []
        for _ in range(2):
            with self.client.websocket_connect("/ws") as ws:
                ws.send_json(start())
                sessions.append(ws.receive_json()["sessionId"])
                until(ws, "asr.transcript")
                ws.send_json(dict(type="asr.stop", requestId="stop", meetingId="meeting-1"))
                _, messages = until(ws, "asr.stopped")
                segments.append(next(m["segment"] for m in messages if m["type"] == "asr.transcript" and m["segment"]["isFinal"]))
        self.assertNotEqual(sessions[0], sessions[1])
        self.assertEqual(segments[1]["seq"], segments[0]["seq"]+1)
        self.assertGreaterEqual(segments[1]["startMs"], segments[0]["endMs"])
        self.assertEqual(repository.pending_count("meeting-1"), 2)

    def test_invalid_control_and_audio_frames_return_errors_without_starting_tasks(self):
        with self.client.websocket_connect("/ws") as ws:
            for value in ["{", '{"type":"unknown"}', '{"type":"asr.start","requestId":"a","meetingId":"m"}']:
                ws.send_text(value)
                self.assertEqual(ws.receive_json()["code"], "INVALID_MESSAGE")
            ws.send_json(dict(type="asr.start", requestId="a", meetingId="m", audio={**AUDIO, "sampleRate": 48000}))
            self.assertEqual(ws.receive_json()["code"], "INVALID_MESSAGE")
            ws.send_bytes(bytes(6400))
            self.assertEqual(ws.receive_json()["code"], "INVALID_STATE")
            self.assertEqual(app.state.asr_meetings, {})

    def test_duplicate_start_and_wrong_meeting_stop_do_not_replace_the_session(self):
        with self.client.websocket_connect("/ws") as ws:
            ws.send_json(start())
            ready = ws.receive_json()
            ws.send_json(start(request="duplicate"))
            error, _ = until(ws, "asr.error")
            self.assertEqual(error["code"], "ALREADY_STARTED")
            self.assertEqual(error["requestId"], "duplicate")
            ws.send_json(dict(type="asr.stop", requestId="wrong", meetingId="other"))
            self.assertEqual(until(ws, "asr.error")[0]["code"], "INVALID_STATE")
            ws.send_json(dict(type="asr.stop", requestId="stop", meetingId="meeting-1"))
            self.assertEqual(until(ws, "asr.stopped")[0]["sessionId"], ready["sessionId"])

    def test_two_connections_cannot_record_the_same_meeting(self):
        with self.client.websocket_connect("/ws") as first:
            first.send_json(start())
            self.assertEqual(first.receive_json()["type"], "asr.ready")
            with self.client.websocket_connect("/ws") as second:
                second.send_json(start())
                self.assertEqual(second.receive_json()["code"], "MEETING_BUSY")
            first.send_json(dict(type="asr.stop", requestId="stop", meetingId="meeting-1"))
            until(first, "asr.stopped")

    def test_failed_save_is_not_published_as_final(self):
        with patch("src.meetings.repository.save_segment", side_effect=OSError("test failure")):
            with self.client.websocket_connect("/ws") as ws:
                ws.send_json(start())
                error, messages = until(ws, "asr.error")
                self.assertEqual(error["code"], "TRANSCRIPT_FAILED")
                self.assertFalse(any(m["type"] == "asr.transcript" and m["segment"]["isFinal"] for m in messages))
                self.assertEqual(repository.pending_count("meeting-1"), 0)
                self.assertTrue(list((Path(self.temporary.name) / "temp/asr/meeting-1").rglob("*.json")))

    @patch("src.providers.asr.doubao.DoubaoSettings.from_config")
    def test_missing_credentials_fail_explicitly_instead_of_losing_audio(self, settings):
        from src.providers.asr.doubao import DoubaoSettings, DoubaoRecognizer
        settings.return_value = DoubaoSettings()
        with patch("src.transport.websocket.DoubaoRecognizer", return_value=DoubaoRecognizer(DoubaoSettings())):
            with self.client.websocket_connect("/ws") as ws:
                ws.send_json(start())
                message = ws.receive_json()
                self.assertEqual(message["code"], "PROVIDER_AUTH_MISSING")
                self.assertEqual(app.state.asr_meetings, {})

    def test_external_page_cannot_connect(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws", headers={"origin": "https://example.com"}):
                pass


    @patch(f"{__name__}.STEP_SECONDS", 1)
    def test_disconnect_preserves_the_unconfirmed_temporary_file(self):
        with self.client.websocket_connect("/ws") as ws:
            ws.send_json(start())
            ready = ws.receive_json()
            partial, _ = until(ws, "asr.transcript")
        directory = Path(self.temporary.name) / "temp/asr/meeting-1" / ready["sessionId"]
        saved = json.loads((directory / "0.json").read_text())
        self.assertEqual(saved["segment"], partial["segment"])
        self.assertEqual(repository.pending_count("meeting-1"), 0)
