"""独立 HTTP 兼容入口，业务处理与 JSON-RPC 共用。"""
import base64
import json
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import config
from ..knowledge.parsers.pdf import MAX_SOURCE_BYTES
from ..meetings.schemas import MinutesOutput
from . import handlers

router = APIRouter(prefix="/internal", tags=["internal"])
Token = Annotated[str | None, Header()]


def authorize(value):
    """验证独立 HTTP 模式的内部服务凭证。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise HTTPException(503, detail={"code": "INTERNAL_NOT_CONFIGURED", "message": "Sidecar 内部服务凭证尚未配置。"})
    if not value or not secrets.compare_digest(value, config.SIDECAR_INTERNAL_TOKEN):
        raise HTTPException(401, detail={"code": "INTERNAL_UNAUTHORIZED", "message": "无效的内部服务凭证。"})


async def execute(method, params, request, token):
    """将兼容 HTTP 请求转换为业务方法调用。"""
    authorize(token)
    try:
        result = await handlers.dispatch(method, params, request.app.state)
    except handlers.OperationError as cause:
        raise HTTPException(cause.status, detail=cause.detail) from cause
    if isinstance(result, handlers.EventStream):
        async def events():
            async for event in result.events:
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        return StreamingResponse(events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return result


@router.post("/agents/chat")
async def agent_chat(body: handlers.AgentInput, request: Request, x_internal_token: Token = None):
    """运行 Agent。"""
    return await execute("agents.chat", body, request, x_internal_token)


@router.post("/agents/title")
async def agent_title(body: handlers.TitleInput, request: Request, x_internal_token: Token = None):
    """生成会话标题。"""
    return await execute("agents.title", body, request, x_internal_token)


@router.get("/agents/models")
async def agent_models(request: Request, x_internal_token: Token = None):
    """查询模型标识。"""
    return await execute("agents.models", {}, request, x_internal_token)


@router.post("/meetings/minutes/generate", response_model=MinutesOutput)
async def generate_minutes(body: handlers.MinutesRequest, request: Request, x_internal_token: Token = None):
    """生成会议纪要。"""
    return await execute("meetings.minutes.generate", body, request, x_internal_token)


@router.post("/knowledge/parse")
async def parse_document(request: Request, x_internal_token: Token = None,
                         file_type: Annotated[Literal["pdf", "txt", "md", "docx"], Query()] = "pdf"):
    """解析源文件。"""
    authorize(x_internal_token)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_SOURCE_BYTES:
            raise HTTPException(413, detail={"message": "文件不能超过 20 MB。"})
    return await execute("knowledge.parse", {"file_type": file_type,
        "content_base64": base64.b64encode(content).decode()}, request, x_internal_token)


@router.post("/knowledge/chunks")
async def chunk_document(body: handlers.ChunkInput, request: Request, x_internal_token: Token = None):
    """父子分块。"""
    return await execute("knowledge.chunks", body, request, x_internal_token)


@router.post("/knowledge/embed")
async def embed_texts(body: handlers.EmbedInput, request: Request, x_internal_token: Token = None):
    """生成向量。"""
    return await execute("knowledge.embed", body, request, x_internal_token)


@router.get("/settings/defaults")
async def service_defaults(request: Request, x_internal_token: Token = None):
    """读取默认参数。"""
    return await execute("settings.defaults", {}, request, x_internal_token)


@router.post("/settings/test")
async def service_test(body: handlers.ConnectionTest, request: Request, x_internal_token: Token = None):
    """测试服务配置。"""
    return await execute("settings.test", body, request, x_internal_token)


@router.post("/asr/sessions")
async def create_asr_session(body: handlers.AsrSessionInput, request: Request, x_internal_token: Token = None):
    """创建 ASR 连接票据。"""
    return await execute("asr.sessions", body, request, x_internal_token)
