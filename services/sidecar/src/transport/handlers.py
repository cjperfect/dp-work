"""按语义方法名分发业务操作，供 JSON-RPC 调用。"""
import asyncio
import base64
import binascii
import secrets
import time
from dataclasses import dataclass
from typing import AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import config
from ..agents.agent import AgentRequest, TitleRequest, generate_title, run_agent, settings_for
from ..harness.runtime import run_events
from ..knowledge.parsers import dispatcher
from ..knowledge.parsers.pdf import MAX_SOURCE_BYTES
from ..knowledge.rag.chunking import split_document
from ..knowledge.rag.embedding import ArkEmbeddings, EmbeddingError, profile
from ..meetings.minutes import generate
from ..meetings.schemas import MinutesInput
from ..providers.llm.schemas import ModelError
from ..providers.settings import RuntimeConfig, defaults, test_connection


class AgentInput(AgentRequest):
    approval_resume: dict[str, dict] | None = None
    run_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9-]{36}$")
    retrieval_token: str | None = Field(default=None, repr=False, max_length=4096)
    runtime: RuntimeConfig | None = None


class TitleInput(TitleRequest):
    runtime: RuntimeConfig | None = None


class MinutesRequest(MinutesInput):
    runtime: RuntimeConfig | None = None


class ConnectionTest(BaseModel):
    kind: Literal["model", "asr"]
    config: RuntimeConfig | None = None


class AsrSessionInput(BaseModel):
    meeting_id: str
    owner_id: int
    runtime: RuntimeConfig | None = None


class ParseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_type: Literal["pdf", "txt", "md", "docx"] = "pdf"
    content_base64: str = Field(max_length=28 * 1024 * 1024, repr=False)


class ChunkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8 * 1024 * 1024)
    metadata: list[dict] = Field(default_factory=list, max_length=1000)


class EmbedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texts: list[str] = Field(min_length=1, max_length=16)
    query: bool = False


class OperationError(Exception):
    """可安全展示的业务错误，状态用于现有 API 兼容适配。"""
    def __init__(self, status, message, code=None):
        super().__init__(message)
        self.status = status
        self.detail = {"message": message, **({"code": code} if code else {})}


@dataclass
class EventStream:
    events: AsyncIterator[dict]


async def agent_chat(params, state):
    """运行 Agent，返回业务事件流。"""
    body = AgentInput.model_validate(params)
    try:
        settings = body.runtime.llm() if body.runtime else settings_for(body.model)
        if body.model and body.model != settings.model:
            raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置，请重新选择模型。")
        body.model = settings.model
    except ModelError as cause:
        raise OperationError(503, str(cause), cause.code) from cause
    return EventStream(run_events(run_agent(body, settings), body.run_id, settings.model))


async def agent_title(params, state):
    """生成会话标题。"""
    body = TitleInput.model_validate(params)
    try:
        settings = body.runtime.llm() if body.runtime else settings_for(body.model)
        if body.model and body.model != settings.model:
            raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置。")
        return {"title": await generate_title(body, settings)}
    except ModelError as cause:
        raise OperationError(503, str(cause), cause.code) from cause


async def agent_models(params, state):
    """读取模型标识，不返回密钥。"""
    return {"configured": bool(config.ARK_API_KEY and config.ARK_MODEL and config.ARK_BASE_URL),
            "models": [{"id": config.ARK_MODEL, "name": config.ARK_MODEL}] if config.ARK_MODEL else []}


async def minutes_generate(params, state):
    """生成会议纪要。"""
    body = MinutesRequest.model_validate(params)
    try:
        result = await generate(body, settings=body.runtime.llm() if body.runtime else None)
        return result.model_dump(mode="json")
    except ModelError as cause:
        raise OperationError(502, str(cause), cause.code) from cause


async def parse_document(params, state):
    """解析源文件字节，不启用 OCR。"""
    body = ParseInput.model_validate(params)
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, binascii.Error) as cause:
        raise OperationError(422, "文件编码无效。") from cause
    if len(content) > MAX_SOURCE_BYTES:
        raise OperationError(413, "文件不能超过 20 MB。")
    if body.file_type == "pdf" and not content.startswith(b"%PDF-"):
        raise OperationError(400, "文件内容不是有效 PDF。")
    try:
        return await dispatcher.parse_document(content, body.file_type)
    except dispatcher.ParseError as cause:
        raise OperationError(422, str(cause)) from cause


async def service_defaults(params, state):
    """读取不含密钥的默认参数。"""
    return defaults()


async def service_test(params, state):
    """测试模型或 ASR 服务配置。"""
    body = ConnectionTest.model_validate(params)
    return await test_connection(body.kind, body.config)


async def asr_session(params, state):
    """创建一次性 ASR 连接票据，与 WebSocket 共用状态。"""
    body = AsrSessionInput.model_validate(params)
    tickets = state.asr_tickets
    now = time.monotonic()
    for key in list(tickets):
        if tickets[key][0] < now:
            tickets.pop(key, None)
    if len(tickets) >= 10000:
        raise OperationError(503, "转写连接繁忙，请稍后重试。")
    ticket = secrets.token_urlsafe(32)
    tickets[ticket] = (now + 60, body.meeting_id, body.owner_id, body.runtime)
    return {"ticket": ticket}


async def chunk_document(params, state):
    """执行父子分块。"""
    body = ChunkInput.model_validate(params)
    try:
        return {"parents": await asyncio.to_thread(split_document, body.content, body.metadata)}
    except EmbeddingError as cause:
        raise OperationError(422, str(cause)) from cause


async def embed_texts(params, state):
    """生成文本向量。"""
    body = EmbedInput.model_validate(params)
    if any(not text.strip() or len(text) > 8000 for text in body.texts) or (body.query and len(body.texts) != 1):
        raise OperationError(422, "向量化文本为空或超出长度限制。")
    try:
        model = ArkEmbeddings()
        async with asyncio.timeout(90):
            vectors = [await model.aembed_query(body.texts[0])] if body.query else await model.aembed_documents(body.texts)
        return {"vectors": vectors, "model": config.EMBEDDING_MODEL, "dimensions": 1024, "profile": profile()}
    except (EmbeddingError, TimeoutError) as cause:
        raise OperationError(502, str(cause) if isinstance(cause, EmbeddingError) else "向量化超时，请重试。") from cause


class SkillsAgent(BaseModel):
    agent_code: Literal["general", "product"]


class SkillsSearch(BaseModel):
    query: str = Field(default="", max_length=200)


class SkillsDescriptions(BaseModel):
    skill_ids: list[str] = Field(max_length=24)


class SkillInstall(SkillsAgent):
    source: str = Field(min_length=1, max_length=512)


class SkillUninstall(SkillsAgent):
    skill_id: str = Field(min_length=1, max_length=256)


async def skill_operation(operation, params):
    """将技能管理错误转换为可展示的业务错误。"""
    from ..skills import service
    try:
        if operation == "descriptions":
            from ..skills.descriptions import descriptions
            body = SkillsDescriptions.model_validate(params)
            return {"items": await descriptions(body.skill_ids)}
        if operation == "search":
            body = SkillsSearch.model_validate(params)
            return {"items": await service.search(body.query)}
        body = (SkillInstall if operation == "install" else SkillUninstall if operation == "uninstall" else SkillsAgent).model_validate(params)
        if operation == "list":
            return {"items": await service.file_operation(service.installed, body.agent_code)}
        if operation == "install":
            return await service.install(body.agent_code, body.source)
        return await service.uninstall(body.agent_code, body.skill_id)
    except service.SkillError as cause:
        raise OperationError(cause.status, str(cause)) from cause


async def skills_descriptions(params, state):
    return await skill_operation("descriptions", params)


async def skills_search(params, state):
    return await skill_operation("search", params)


async def skills_list(params, state):
    return await skill_operation("list", params)


async def skills_install(params, state):
    return await skill_operation("install", params)


async def skills_uninstall(params, state):
    return await skill_operation("uninstall", params)


class AgentConfigInput(BaseModel):
    agent_code: Literal["general", "product"]


async def agent_config(params, state):
    """读取当前设备指定 Agent 的提示词配置。"""
    from ..agents.context import read_prompt
    body = AgentConfigInput.model_validate(params)
    try:
        prompt = await asyncio.to_thread(read_prompt, body.agent_code)
    except ModelError as cause:
        raise OperationError(400, str(cause)) from cause
    return {"agent_code": body.agent_code, "prompt": prompt, "prompt_file": "AGENT.md"}


class AgentConfigUpdate(AgentConfigInput):
    prompt: str = Field(min_length=1, max_length=65536)
    expected_prompt: str = Field(min_length=1, max_length=65536)


async def agent_config_update(params, state):
    """保存当前设备指定 Agent 的提示词。"""
    from ..agents.context import save_prompt
    body = AgentConfigUpdate.model_validate(params)
    try:
        prompt = await asyncio.to_thread(save_prompt, body.agent_code, body.prompt, body.expected_prompt)
    except ModelError as cause:
        status = 409 if cause.code == "AGENT_PROMPT_CONFLICT" else 500 if cause.code == "AGENT_PROMPT_SAVE_FAILED" else 400
        raise OperationError(status, str(cause)) from cause
    return {"agent_code": body.agent_code, "prompt": prompt, "prompt_file": "AGENT.md"}


HANDLERS = {
    "agents.config.update": agent_config_update,
    "agents.config": agent_config,
    "skills.search": skills_search,
    "skills.descriptions": skills_descriptions,
    "skills.list": skills_list,
    "skills.install": skills_install,
    "skills.uninstall": skills_uninstall,
    "agents.chat": agent_chat,
    "agents.title": agent_title,
    "agents.models": agent_models,
    "meetings.minutes.generate": minutes_generate,
    "knowledge.parse": parse_document,
    "knowledge.chunks": chunk_document,
    "knowledge.embed": embed_texts,
    "settings.defaults": service_defaults,
    "settings.test": service_test,
    "asr.sessions": asr_session,
}


async def dispatch(method, params, state):
    """方法名直接对应处理函数，不经过 HTTP 路由。"""
    return await HANDLERS[method](params, state)
