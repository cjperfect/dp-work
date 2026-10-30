"""方舟多模态 Embedding 的纯文本适配。"""
import asyncio
import hashlib
import json
import math
from uuid import uuid4
from ...usage.ledger import write, raw_usage
from weakref import WeakKeyDictionary
from urllib.parse import urlsplit
import httpx
from langchain_core.embeddings import Embeddings
from ... import config

CORPUS_INSTRUCTION = "Instruction:Compress the text into one word.\nQuery:"
QUERY_INSTRUCTION = "Target_modality: text.\nInstruction:根据这个问题，检索可以回答问题的相关文档。\nQuery:"


class EmbeddingError(ValueError):
    """可安全展示的向量服务错误。"""


def profile() -> str:
    """标识向量空间，避免不同配置的向量混用。"""
    data = [config.EMBEDDING_MODEL, config.EMBEDDING_DIMENSIONS, config.EMBEDDING_BASE_URL,
            CORPUS_INSTRUCTION, QUERY_INSTRUCTION, "parent-child-v1"]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def validate_vector(value):
    """检查向量维度、有限数值和非零模长。"""
    if not isinstance(value, list) or len(value) != 1024:
        raise EmbeddingError("向量服务返回的维度不是 1024。")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in value) or not any(value):
        raise EmbeddingError("向量服务返回了无效向量。")
    return value


class ArkEmbeddings(Embeddings):
    """每个文本单独生成向量，限制并发并重试瞬时错误。"""
    def embed_documents(self, texts):
        raise NotImplementedError("请使用异步向量化接口")

    def embed_query(self, text):
        raise NotImplementedError("请使用异步向量化接口")

    async def _embed(self, texts: list[str], query: bool):
        url = urlsplit(config.EMBEDDING_BASE_URL)
        if not config.EMBEDDING_API_KEY:
            raise EmbeddingError("请在 Sidecar .env 中配置 EMBEDDING_API_KEY。")
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise EmbeddingError("请配置有效的 Embedding HTTPS 地址。")
        if config.EMBEDDING_DIMENSIONS != 1024:
            raise EmbeddingError("当前向量索引使用 1024 维，请保持配置一致。")
        async with httpx.AsyncClient(timeout=config.EMBEDDING_TIMEOUT_SECONDS, follow_redirects=False) as client:
            async def one(text):
                async with limiter():
                    for attempt in range(3):
                        try:
                            call_id = str(uuid4())
                            await asyncio.to_thread(write, call_id, config.EMBEDDING_MODEL, status='unreported', category='embedding')
                            response = await client.post(config.EMBEDDING_BASE_URL + "/embeddings/multimodal",
                                headers={"Authorization": "Bearer " + config.EMBEDDING_API_KEY},
                                json={"model": config.EMBEDDING_MODEL, "input": [{"type": "text", "text": text}],
                                      "dimensions": 1024, "encoding_format": "float",
                                      "instructions": QUERY_INSTRUCTION if query else CORPUS_INSTRUCTION})
                            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                                await asyncio.sleep(0.5 * 2 ** attempt)
                                continue
                            if response.status_code != 200:
                                raise EmbeddingError(f"方舟向量化请求失败（HTTP {response.status_code}），请检查密钥和模型权限。")
                            data = response.json()
                            usage = raw_usage(data)
                            await asyncio.to_thread(write, call_id, config.EMBEDDING_MODEL, usage,
                                                    status='reported' if usage is not None else 'unreported', category='embedding')
                            return validate_vector(data.get("data", {}).get("embedding"))
                        except (httpx.TimeoutException, httpx.NetworkError) as cause:
                            if attempt == 2:
                                raise EmbeddingError("向量服务连接超时或中断，请重试。") from cause
                            await asyncio.sleep(0.5 * 2 ** attempt)
                        except (ValueError, TypeError, AttributeError) as cause:
                            if isinstance(cause, EmbeddingError):
                                raise
                            raise EmbeddingError("向量服务返回了无效数据。") from cause
            tasks = [asyncio.create_task(one(text)) for text in texts]
            try:
                return await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def aembed_documents(self, texts):
        return await self._embed(texts, False)

    async def aembed_query(self, text):
        return (await self._embed([text], True))[0]


_limiters = WeakKeyDictionary()


def limiter():
    """同一事件循环共享并发限制，兼容测试与应用重启。"""
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = asyncio.Semaphore(4)
    return _limiters[loop]
