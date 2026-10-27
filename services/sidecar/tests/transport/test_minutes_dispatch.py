"""纪要通过语义方法分发，不暴露模型凭证。"""
import asyncio
from unittest.mock import AsyncMock, patch
from src.transport.handlers import dispatch
from src.meetings.schemas import MinutesOutput

BODY = {"task_id": "task", "meeting_id": "meeting", "source_revision": 1,
        "title": "会议", "scheduled_at": "2026-10-26T02:00:00Z",
        "segments": [{"id": "one", "seq": 0, "text": "确认需求", "start_ms": 0}]}


def test_minutes_dispatch_response():
    async def case():
        output = MinutesOutput(task_id="task", source_revision=1, content="# 会议", model="test-model", prompt_version="minutes-v1")
        with patch("src.transport.handlers.generate", new=AsyncMock(return_value=output)) as generate:
            response = await dispatch("meetings.minutes.generate", BODY, None)
            assert response["prompt_version"] == "minutes-v1"
            assert "api_key" not in str(response)
            generate.assert_awaited_once()
    asyncio.run(case())
