"""内部生成接口需要服务鉴权，不向客户端暴露模型凭证。"""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from src.main import app
from src import config
from src.meetings.schemas import MinutesOutput

BODY = {"task_id": "task", "meeting_id": "meeting", "source_revision": 1,
        "title": "会议", "scheduled_at": "2026-10-26T02:00:00Z",
        "segments": [{"id": "one", "seq": 0, "text": "确认需求", "start_ms": 0}]}


class InternalMinutesTests(unittest.TestCase):
    def test_internal_auth_and_response(self):
        with patch.object(config, "SIDECAR_INTERNAL_TOKEN", "internal-fixture"), TestClient(app) as client:
            self.assertEqual(client.post("/internal/meetings/minutes/generate", json=BODY).status_code, 401)
            output = MinutesOutput(task_id="task", source_revision=1, content="# 会议", model="test-model", prompt_version="minutes-v1")
            with patch("src.transport.handlers.generate", new=AsyncMock(return_value=output)) as generate:
                response = client.post("/internal/meetings/minutes/generate", json=BODY, headers={"X-Internal-Token": "internal-fixture"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["prompt_version"], "minutes-v1")
                self.assertNotIn("api_key", response.text)
                generate.assert_awaited_once()
