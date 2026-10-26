"""方舟模型请求使用本地 HTTP 替身，不调用付费服务。"""
import json
import unittest
from httpx import MockTransport, Response
from src.providers.llm.client import complete
from src.providers.llm.schemas import ModelError, ModelSettings
from src.meetings.minutes import generate, messages, SECTIONS
from src.meetings.schemas import MinutesInput

CONTENT = "# 测试会议\n\n" + "\n\n".join(f"## {section}\n未明确" for section in SECTIONS)


def source():
    return MinutesInput(task_id="task-1", meeting_id="meeting-1", source_revision=3, title="评审会议",
        scheduled_at="2026-10-26T02:00:00Z", segments=[{"id": "segment-1", "seq": 0, "speaker": "说话人1", "text": "先做 PDF。", "start_ms": 12000}])


class ArkTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_auth_prompt_and_structured_result(self):
        requests = []
        async def handler(request):
            requests.append(request)
            return Response(200, json={"model": "actual-model", "choices": [{"finish_reason": "stop", "message": {"content": CONTENT}}]})
        result = await generate(source(), ModelSettings(api_key="test-secret"), MockTransport(handler))
        self.assertEqual(result.content, CONTENT)
        self.assertEqual(result.source_revision, 3)
        self.assertEqual(result.prompt_version, "minutes-v1")
        self.assertEqual(result.model, "actual-model")
        request = requests[0]
        self.assertEqual(str(request.url), "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
        body = json.loads(request.content)
        self.assertEqual(body["model"], "deepseek-v4-1-flash-261017")
        self.assertFalse(body["stream"])
        self.assertIn("不得编造", body["messages"][0]["content"])
        self.assertIn("segment-1", body["messages"][1]["content"])
        self.assertIn("00:00:12", body["messages"][1]["content"])
        self.assertIn("10:00:00+08:00", body["messages"][1]["content"])

    async def test_missing_key_never_calls_provider(self):
        def unexpected(_request):
            self.fail("不应请求模型")
        with self.assertRaises(ModelError) as error:
            await generate(source(), ModelSettings(), MockTransport(unexpected))
        self.assertEqual(error.exception.code, "MODEL_NOT_CONFIGURED")

    async def test_safe_errors_and_no_truncated_or_empty_minutes(self):
        responses = [
            (401, {"error": "secret upstream"}, "MODEL_AUTH_FAILED"),
            (429, {"error": "secret upstream"}, "MODEL_RATE_LIMIT"),
            (500, {"error": "secret upstream"}, "MODEL_REQUEST_FAILED"),
            (200, {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}, "MODEL_INCOMPLETE"),
            (200, {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}, "MODEL_INVALID_RESPONSE"),
            (200, {"choices": [{"finish_reason": "stop", "message": {"content": "not minutes"}}]}, "MINUTES_FORMAT_INVALID"),
        ]
        for status, body, code in responses:
            with self.subTest(code=code):
                with self.assertRaises(ModelError) as error:
                    await generate(source(), ModelSettings(api_key="fixture"), MockTransport(lambda request: Response(status, json=body)))
                self.assertEqual(error.exception.code, code)
                self.assertNotIn("secret upstream", str(error.exception))

    async def test_long_input_is_rejected_without_silent_truncation(self):
        body = source()
        body.segments[0].text = "a" * 130000
        with self.assertRaises(ModelError) as error:
            messages(body)
        self.assertEqual(error.exception.code, "MEETING_TOO_LONG")
