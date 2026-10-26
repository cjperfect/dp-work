"""供 API 服务调用的内部模型接口。"""
import secrets
import asyncio
import json
from typing import Annotated, Literal
from fastapi import APIRouter, Header, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from ..agents.agent import AgentRequest, run_agent, settings_for
from .. import config
from ..knowledge.parsers import dispatcher
from ..knowledge.parsers.pdf import MAX_SOURCE_BYTES
from ..meetings.minutes import generate
from ..meetings.schemas import MinutesInput, MinutesOutput
from ..providers.llm.schemas import ModelError
from ..knowledge.rag.chunking import split_document
from ..knowledge.rag.embedding import ArkEmbeddings, EmbeddingError, profile
from ..providers.settings import RuntimeConfig, defaults, test_connection
from pydantic import BaseModel, ConfigDict, Field

class InternalAgentRequest(AgentRequest):
    retrieval_token: str | None = Field(default=None, repr=False, max_length=4096)
    runtime: RuntimeConfig | None = None


class InternalMinutesInput(MinutesInput):
    runtime: RuntimeConfig | None = None


class ConnectionTest(BaseModel):
    kind: Literal["model", "asr"]
    config: RuntimeConfig | None = None


router = APIRouter(prefix="/internal", tags=["internal"])


def authorize(value: str | None):
    """验证 API 与 Sidecar 的服务凭证。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise HTTPException(503, detail={"code": "INTERNAL_NOT_CONFIGURED", "message": "Sidecar 内部服务凭证尚未配置。"})
    if not value or not secrets.compare_digest(value, config.SIDECAR_INTERNAL_TOKEN):
        raise HTTPException(401, detail={"code": "INTERNAL_UNAUTHORIZED", "message": "无效的内部服务凭证。"})


@router.post("/meetings/minutes/generate", response_model=MinutesOutput)
async def generate_minutes(body: InternalMinutesInput, x_internal_token: Annotated[str | None, Header()] = None):
    """生成会议纪要，密钥和模型调用仅在服务端处理。"""
    authorize(x_internal_token)
    try:
        return await generate(body, settings=body.runtime.llm() if body.runtime else None)
    except ModelError as cause:
        raise HTTPException(502, detail={"code": cause.code, "message": str(cause)}) from cause


@router.post("/knowledge/parse", summary="解析 TXT、Markdown、PDF 或 DOCX 文档")
async def parse_document(request: Request, x_internal_token: Annotated[str | None, Header()] = None,
                         file_type: Annotated[Literal["pdf", "txt", "md", "docx"], Query()] = "pdf"):
    """接收源文件字节，返回解析正文，不启用 OCR。"""
    authorize(x_internal_token)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_SOURCE_BYTES:
            raise HTTPException(413, detail={"message": "文件不能超过 20 MB。"})
    if file_type == "pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(400, detail={"message": "文件内容不是有效 PDF。"})
    try:
        return await dispatcher.parse_document(bytes(content), file_type)
    except dispatcher.ParseError as cause:
        raise HTTPException(422, detail={"message": str(cause)}) from cause


@router.get("/agents/models", summary="查询实际配置的 Agent 模型")
async def agent_models(x_internal_token: Annotated[str | None, Header()] = None):
    """只返回模型标识及配置状态，不返回密钥。"""
    authorize(x_internal_token)
    return {"configured": bool(config.ARK_API_KEY and config.ARK_MODEL and config.ARK_BASE_URL),
            "models": [{"id": config.ARK_MODEL, "name": config.ARK_MODEL}] if config.ARK_MODEL else []}


@router.post("/agents/chat", summary="运行 LangGraph Agent")
async def agent_chat(body: InternalAgentRequest, x_internal_token: Annotated[str | None, Header()] = None):
    """校验模型配置后流式返回运行事件。"""
    authorize(x_internal_token)
    try:
        settings = body.runtime.llm() if body.runtime else settings_for(body.model)
        if body.model and body.model != settings.model:
            raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置，请重新选择模型。")
        body.model = settings.model
    except ModelError as cause:
        raise HTTPException(503, detail={"message": str(cause)}) from cause
    async def events():
        async for event in run_agent(body, settings):
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/settings/defaults", summary="读取无密钥的平台默认配置")
async def service_defaults(x_internal_token: Annotated[str | None, Header()] = None):
    """返回平台默认参数。"""
    authorize(x_internal_token)
    return defaults()


@router.post("/settings/test", summary="测试服务连接")
async def service_test(body: ConnectionTest, x_internal_token: Annotated[str | None, Header()] = None):
    """测试可信 API 提交的配置。"""
    authorize(x_internal_token)
    return await test_connection(body.kind, body.config)


class AsrSessionInput(BaseModel):
    meeting_id: str
    owner_id: int
    runtime: RuntimeConfig | None = None


@router.post("/asr/sessions", summary="创建短时转写连接凭证")
async def create_asr_session(body: AsrSessionInput, request: Request,
    x_internal_token: Annotated[str | None, Header()] = None):
    """将个人凭证留在服务端，浏览器只获得一次性连接票据。"""
    import time
    authorize(x_internal_token)
    now = time.monotonic()
    tickets = request.app.state.asr_tickets
    for key in list(tickets):
        if tickets[key][0] < now:
            tickets.pop(key, None)
    if len(tickets) >= 10000:
        raise HTTPException(503, detail={"message": "转写连接繁忙，请稍后重试。"})
    ticket = secrets.token_urlsafe(32)
    tickets[ticket] = (now + 60, body.meeting_id, body.owner_id, body.runtime)
    return {"ticket": ticket}




class ChunkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8 * 1024 * 1024)
    metadata: list[dict] = Field(default_factory=list, max_length=1000)


class EmbedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texts: list[str] = Field(min_length=1, max_length=16)
    query: bool = False


@router.post("/knowledge/chunks", summary="父子分块")
async def chunk_document(body: ChunkInput, x_internal_token: Annotated[str | None, Header()] = None):
    """按标题拆分解析正文，返回父块与子块。"""
    authorize(x_internal_token)
    try:
        return {"parents": await asyncio.to_thread(split_document, body.content, body.metadata)}
    except EmbeddingError as cause:
        raise HTTPException(422, detail={"message": str(cause)}) from cause


@router.post("/knowledge/embed", summary="文本向量化")
async def embed_texts(body: EmbedInput, x_internal_token: Annotated[str | None, Header()] = None):
    """子块逐条向量化，避免将多个子块融合为一个向量。"""
    authorize(x_internal_token)
    if any(not text.strip() or len(text) > 8000 for text in body.texts) or (body.query and len(body.texts) != 1):
        raise HTTPException(422, detail={"message": "向量化文本为空或超出长度限制。"})
    try:
        model = ArkEmbeddings()
        async with asyncio.timeout(90):
            vectors = [await model.aembed_query(body.texts[0])] if body.query else await model.aembed_documents(body.texts)
        return {"vectors": vectors, "model": config.EMBEDDING_MODEL, "dimensions": 1024, "profile": profile()}
    except (EmbeddingError, TimeoutError) as cause:
        raise HTTPException(502, detail={"message": str(cause) if isinstance(cause, EmbeddingError) else "向量化超时，请重试。"}) from cause
