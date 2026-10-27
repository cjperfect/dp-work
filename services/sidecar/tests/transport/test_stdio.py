"""管道协议、流式取消和真实 Sidecar 入口回归。"""
import asyncio
import base64
import io
import json
import os
import socket
import sys
from pathlib import Path

import httpx

from src.transport.stdio import StdioServer
from src.transport import handlers
from unittest.mock import patch


def test_stdio_stream_ids_and_cancel():
    async def case():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def events():
            started.set()
            try:
                yield {"type": "delta", "text": "delta"}
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def dispatch(method, params, state):
            assert method == "agents.chat" and params == {"message": "payload"}
            return handlers.EventStream(events())
        output = io.BytesIO()
        rpc = StdioServer(None, output)
        with patch.object(handlers, "dispatch", dispatch):
            await rpc.handle(json.dumps({"jsonrpc": "2.0", "id": "stream", "method": "agents.chat",
                "params": {"message": "payload"}}))
            await asyncio.wait_for(started.wait(), 2)
        await rpc.handle('{"jsonrpc":"2.0","id":"health","method":"system.health"}')
        await rpc.handle('{"jsonrpc":"2.0","method":"$/cancelRequest","params":{"id":"stream"}}')
        await asyncio.wait_for(cancelled.wait(), 2)
        await rpc.close()
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        assert rows[0]["method"] == "stream.head"
        assert rows[1]["params"]["id"] == "stream"
        assert b"delta" in base64.b64decode(rows[1]["params"]["data"])
        assert any(row.get("id") == "health" and row["result"]["ok"] for row in rows)
        assert any(row.get("id") == "stream" and row.get("error", {}).get("code") == -32800 for row in rows)
    asyncio.run(case())


def test_stdio_invalid_frames_do_not_execute():
    async def case():
        output = io.BytesIO()
        rpc = StdioServer(None, output)
        for raw in ['{', '[]', '{"jsonrpc":"2.0","id":"bad","method":"shell.exec"}',
                    '{"jsonrpc":"2.0","id":"params","method":"agents.chat","params":{"data":"???"}}']:
            await rpc.handle(raw)
        await asyncio.gather(*list(rpc.tasks.values()))
        codes = [json.loads(line)["error"]["code"] for line in output.getvalue().splitlines()]
        assert codes == [-32700, -32600, -32601, -32602]
    asyncio.run(case())


def test_real_stdio_entry_shares_asr_state_and_disables_network_internal(tmp_path):
    async def case():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env_file = tmp_path / "sidecar.env"
        env_file.write_text("")
        environment = {**os.environ, "PORT": str(port), "DP_SIDECAR_ENV_FILE": str(env_file),
            "DP_DATA_DIR": str(tmp_path / "data"), "SIDECAR_INTERNAL_TOKEN": "",
            "ARK_API_KEY": "", "VOLC_API_KEY": ""}
        log = (tmp_path / "stderr.log").open("wb")
        command = [os.environ["SIDECAR_TEST_EXECUTABLE"], "--stdio"] if os.environ.get("SIDECAR_TEST_EXECUTABLE") else [sys.executable, "desktop_entry.py", "--stdio"]
        child = await asyncio.create_subprocess_exec(*command,
            cwd=Path(__file__).resolve().parents[2], env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log)
        async def read():
            raw = await asyncio.wait_for(child.stdout.readline(), 15)
            assert raw, (tmp_path / "stderr.log").read_text()
            return json.loads(raw)
        async def call(key, method, body=None, query=""):
            params = {"file_type": query.split("=")[-1], "content_base64": base64.b64encode(body).decode()} if isinstance(body, bytes) else body or {}
            child.stdin.write((json.dumps({"jsonrpc": "2.0", "id": key, "method": method,
                "params": params}) + "\n").encode())
            await child.stdin.drain()
            chunks = bytearray()
            while True:
                row = await read()
                assert row.get("id", row.get("params", {}).get("id")) == key
                assert "error" not in row, row
                if row.get("method") == "stream.chunk":
                    chunks.extend(base64.b64decode(row["params"]["data"]))
                if "result" in row:
                    return json.loads(chunks) if chunks else row["result"]
        try:
            for index in range(80):
                state = await call(str(index), "system.health")
                if state["ok"]:
                    break
                await asyncio.sleep(.1)
            assert state["ok"]
            parsed = await call("parse", "knowledge.parse", b"# Pipe test\nhello", "file_type=md")
            assert "hello" in parsed["content"]
            ticket = await call("ticket", "asr.sessions", {"meeting_id": "stdio-test", "owner_id": 1})
            assert len(ticket["ticket"]) > 20
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://127.0.0.1:{port}/internal/settings/defaults")
                assert response.status_code == 404
                assert (await client.get(f"http://127.0.0.1:{port}/health")).status_code == 200
            # 通过 WebSocket 消费管道创建的票据；有效票据会进入服务凭证校验。
            import websockets
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
                await ws.send(json.dumps({"type": "asr.start", "requestId": "request", "meetingId": "stdio-test", "ticket": ticket["ticket"], "audio": {"format": "pcm", "sampleRate": 16000, "channels": 1, "bitsPerSample": 16}, "nextSeq": 0, "offsetMs": 0}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), 3))
                assert reply.get("code") not in ("INVALID_TICKET", "INVALID_MESSAGE"), reply
            child.stdin.close()
            assert await asyncio.wait_for(child.wait(), 10) == 0
        finally:
            if child.returncode is None:
                child.kill()
                await child.wait()
            log.close()
    asyncio.run(case())


def test_registered_methods_match_shared_protocol():
    from src.transport.protocol import METHODS
    assert set(handlers.HANDLERS) == METHODS


def test_network_surface_has_no_business_http_routes():
    from fastapi.testclient import TestClient
    from src.main import app
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        for path in ("/internal/agents/models", "/internal/agents/chat", "/internal/asr/sessions",
                     "/internal/knowledge/parse", "/internal/meetings/minutes/generate"):
            assert client.get(path).status_code == 404
            assert client.post(path, json={}).status_code == 404
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "invalid"})
            assert ws.receive_json()["code"] == "INVALID_MESSAGE"
