"""统一模型客户端的结构化输出、兼容降级与重试边界。"""

import asyncio
import json
import httpx
import pytest
from pydantic import BaseModel
from src.providers.llm.client import complete, complete_structured
from src.providers.llm.schemas import ModelSettings, ModelError
from src.usage.ledger import scope, summary
from src import config


class Result(BaseModel):
    answer: str


SETTINGS = ModelSettings(
    api_key="fixture", model="fixture", base_url="https://model.test/v3"
)
MESSAGES = [{"role": "user", "content": "Return JSON with answer."}]


def response(content, finish="stop"):
    return httpx.Response(
        200,
        json={
            "model": "fixture",
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def test_native_json_mode_and_schema_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    requests = []

    def upstream(request):
        requests.append(json.loads(request.content))
        return response('{"answer":"正确"}')

    async def run():
        with scope(7):
            result = await complete_structured(
                MESSAGES, SETTINGS, Result, httpx.MockTransport(upstream)
            )
        assert result.answer == "正确"
        assert requests[0]["response_format"] == {"type": "json_object"}
        assert summary(7)["items"][0]["calls"] == 1
        assert summary(7)["items"][0]["total_tokens"] == 15

    asyncio.run(run())


@pytest.mark.parametrize("unsupported", [True, False])
def test_fallback_only_when_json_mode_is_explicitly_unsupported(unsupported):
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "response_format is unsupported"
                        if unsupported
                        else "invalid model"
                    }
                },
            )
        return response('```json\n{"answer":"compatible"}\n```')

    async def run():
        if unsupported:
            result = await complete_structured(
                MESSAGES, SETTINGS, Result, httpx.MockTransport(upstream)
            )
            assert result.answer == "compatible"
            assert len(calls) == 2 and "response_format" not in calls[1]
        else:
            with pytest.raises(ModelError) as error:
                await complete_structured(
                    MESSAGES, SETTINGS, Result, httpx.MockTransport(upstream)
                )
            assert error.value.code == "MODEL_REQUEST_FAILED" and len(calls) == 1

    asyncio.run(run())


def test_invalid_structure_still_records_reported_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)

    async def run():
        with scope(7), pytest.raises(ModelError, match="结构"):
            await complete_structured(
                MESSAGES,
                SETTINGS,
                Result,
                httpx.MockTransport(lambda _: response('{"wrong":"field"}')),
            )
        assert summary(7)["items"][0]["total_tokens"] == 15

    asyncio.run(run())


def test_rate_limit_does_not_retry_or_expose_upstream_text():
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(
            429, json={"error": {"message": "private upstream payload"}}
        )

    async def run():
        with pytest.raises(ModelError) as error:
            await complete(MESSAGES, SETTINGS, httpx.MockTransport(upstream))
        assert error.value.code == "MODEL_RATE_LIMIT"
        assert "private" not in str(error.value) and len(calls) == 1

    asyncio.run(run())
