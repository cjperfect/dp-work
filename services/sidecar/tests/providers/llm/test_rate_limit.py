"""验证真实 LangChain 适配器在网络调用前执行限流，覆盖流式和非流式。"""
import asyncio
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from src.providers.llm.chat import ReasoningChatOpenAI
from src.providers.llm.schemas import ModelError


def test_nonstream_and_stream_are_guarded_before_network():
    async def case():
        def forbidden(request):
            raise AssertionError('限流拒绝后不能请求模型服务')
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
            model = ReasoningChatOpenAI(model='test', api_key='test', base_url='https://example.test',
                                        http_async_client=client, max_retries=0)
            gate = AsyncMock(side_effect=ModelError('MODEL_RATE_LIMIT', 'too many'))
            with patch('src.providers.llm.redis_control.permit', gate):
                with pytest.raises(ModelError):
                    await model.ainvoke('hello')
                with pytest.raises(ModelError):
                    async for _ in model.astream('hello'):
                        pass
            assert gate.await_count == 2
    asyncio.run(case())
