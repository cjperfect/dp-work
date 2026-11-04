"""按语义方法名分发业务操作，供 JSON-RPC 调用。"""
import asyncio
import base64
import binascii
import secrets
import time
from functools import partial
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import config
from .protocol import METHODS
from .types import OperationError, EventStream, LocalSettingsInput
from .operations.skills import skill_operation
from .operations.projects import project_operation
from .operations.connectors import connector_operation
from .operations.sessions import session_operation
from .operations.memory import memory_operation
from .operations.usage import usage_summary, usage_settings
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
from ..providers import local_settings


class AgentInput(AgentRequest):
    memory_context: str = Field(default='', max_length=5000, repr=False)
    execution_context: str = Field(default='', max_length=18000, repr=False)
    project_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9-]{36}$")
    workspace_owner_id: int | None = Field(default=None, gt=0)
    checkpoint_resume: bool = False
    approval_resume: dict[str, dict] | None = None
    run_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9-]{36}$")
    retrieval_token: str | None = Field(default=None, repr=False, max_length=4096)
    runtime: RuntimeConfig | None = None


class TitleInput(TitleRequest):
    owner_id: int | None = Field(default=None, gt=0)
    runtime: RuntimeConfig | None = None


class SteeringInput(BaseModel):
    run_id: str = Field(pattern=r'^[a-fA-F0-9-]{36}$')
    owner_id: int = Field(gt=0)
    thread_id: str = Field(min_length=1, max_length=128)
    id: str = Field(pattern=r'^[a-fA-F0-9-]{36}$')
    content: str = Field(min_length=1, max_length=120000)


async def agent_steer(params, state):
    """将补充指令投递到正在运行的 Agent，下一轮模型调用前消费。"""
    from ..harness.steering import deliver
    body = SteeringInput.model_validate(params)
    try:
        deliver(body.run_id, body.owner_id, body.thread_id, body.id, body.content)
    except ValueError as cause:
        raise OperationError(409, str(cause)) from cause
    return {'id': body.id, 'status': 'queued'}


class MinutesRequest(MinutesInput):
    owner_id: int | None = Field(default=None, gt=0)
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


async def agent_chat(params, state):
    """运行 Agent，返回业务事件流。"""
    body = AgentInput.model_validate(params)
    try:
        personal = body.runtime or await asyncio.to_thread(local_settings.runtime, getattr(body, "owner_id", None) or getattr(body, "workspace_owner_id", None), "model")
        settings = personal.llm() if personal else settings_for(body.model)
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
        personal = body.runtime or await asyncio.to_thread(local_settings.runtime, getattr(body, "owner_id", None) or getattr(body, "workspace_owner_id", None), "model")
        settings = personal.llm() if personal else settings_for(body.model, task_type="title")
        if body.model and body.model != settings.model:
            raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置。")
        return {"title": await generate_title(body, settings)}
    except ModelError as cause:
        raise OperationError(503, str(cause), cause.code) from cause


async def agent_models(params, state):
    """读取模型标识，不返回密钥。"""
    personal = await asyncio.to_thread(local_settings.runtime, params.get("owner_id"), "model")
    if personal:
        return {"configured": True, "models": [{"id": personal.model, "name": personal.model}]}
    return {"configured": bool(config.ARK_API_KEY and config.ARK_MODEL and config.ARK_BASE_URL),
            "models": [{"id": config.ARK_MODEL, "name": config.ARK_MODEL}] if config.ARK_MODEL else []}


async def minutes_generate(params, state):
    """生成会议纪要。"""
    body = MinutesRequest.model_validate(params)
    try:
        personal = body.runtime or await asyncio.to_thread(local_settings.runtime, body.owner_id, "model")
        result = await generate(body, settings=personal.llm() if personal else None)
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


async def local_service_settings(action, params, state):
    """仅返回去除密钥后的本机设置与测试结果。"""
    body = LocalSettingsInput.model_validate(params)
    try:
        if action == "read":
            return await asyncio.to_thread(local_settings.read, body.owner_id)
        if action == "save":
            return await asyncio.to_thread(local_settings.save, body.owner_id, body.kind, body.body)
        if action == "configured":
            personal = await asyncio.to_thread(local_settings.runtime, body.owner_id, body.kind)
            return {"configured": bool(personal) or defaults()[body.kind]["configured"]}
        override = await asyncio.to_thread(local_settings.test_config, body.owner_id, body.kind, body.body)
        return await test_connection(body.kind, override)
    except ValueError as cause:
        raise OperationError(400, str(cause)) from cause


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
    personal = body.runtime or await asyncio.to_thread(local_settings.runtime, body.owner_id, "asr")
    tickets[ticket] = (now + 60, body.meeting_id, body.owner_id, personal)
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
    except ModelError as cause:
        raise OperationError(429 if cause.code == "MODEL_RATE_LIMIT" else 503, str(cause), cause.code) from cause
    except (EmbeddingError, TimeoutError) as cause:
        raise OperationError(502, str(cause) if isinstance(cause, EmbeddingError) else "向量化超时，请重试。") from cause


class AgentConfigInput(BaseModel):
    agent_code: Literal["general", "product", "ui"]


class AgentKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner_id: int = Field(gt=0)
    body: dict = Field(default_factory=dict)


async def agent_knowledge(action, params, state):
    """只在已验证账号的本机数据库读写知识库关联。"""
    import sqlite3
    from ..agents.knowledge import operation
    body = AgentKnowledgeInput.model_validate(params)
    try:
        return await asyncio.to_thread(operation, action, body.owner_id, body.body)
    except ValidationError as cause:
        raise OperationError(400, '知识库关联参数无效。') from cause
    except (sqlite3.DatabaseError, OSError) as cause:
        raise OperationError(500, '知识库关联保存失败，请检查本地数据库。') from cause


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
    "connectors.feishu.status": partial(connector_operation, "status"),
    "connectors.feishu.verify": partial(connector_operation, "verify"),
    "connectors.feishu.start": partial(connector_operation, "start"),
    "connectors.feishu.cancel": partial(connector_operation, "cancel"),
    "connectors.feishu.disconnect": partial(connector_operation, "disconnect"),

    "projects.list": partial(project_operation, "list"),
    "projects.create": partial(project_operation, "create"),
    "projects.get": partial(project_operation, "get"),
    "projects.rename": partial(project_operation, "rename"),
    "projects.delete": partial(project_operation, "delete"),

    "settings.read": partial(local_service_settings, "read"),
    "settings.save": partial(local_service_settings, "save"),
    "settings.configured": partial(local_service_settings, "configured"),
    "settings.test-local": partial(local_service_settings, "test-local"),

    "agents.steer": agent_steer,
    "agents.config.update": agent_config_update,
    "agents.config": agent_config,
    "agents.knowledge.read": partial(agent_knowledge, 'read'),
    "agents.knowledge.save": partial(agent_knowledge, 'save'),
    "agents.knowledge.import": partial(agent_knowledge, 'import'),
    "skills.search": partial(skill_operation, "search"),
    "skills.descriptions": partial(skill_operation, "descriptions"),
    "skills.list": partial(skill_operation, "list"),
    "skills.upload": partial(skill_operation, "upload"),
    "skills.install": partial(skill_operation, "install"),
    "skills.uninstall": partial(skill_operation, "uninstall"),
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
    "usage.summary": usage_summary,
    "usage.settings.read": partial(usage_settings, "read"),
    "usage.settings.save": partial(usage_settings, "save"),
    **{method: partial(session_operation, method.removeprefix("sessions."))
       for method in METHODS if method.startswith("sessions.")},
    **{method: partial(memory_operation, method.removeprefix("memory."))
       for method in METHODS if method.startswith("memory.")},
}


async def dispatch(method, params, state):
    """方法名直接对应处理函数，不经过 HTTP 路由。"""
    from ..usage.ledger import scope
    params = dict(params)
    owner = params.pop('_usage_owner_id', None) or params.get('owner_id') or params.get('workspace_owner_id')
    category = {'agents.title':'title', 'meetings.minutes.generate':'minutes', 'knowledge.embed':'embedding'}.get(method, 'agent')
    reference = params.get('run_id') or params.get('task_id') or params.get('thread_id')
    with scope(owner, category, reference):
        result = await HANDLERS[method](params, state)
    if isinstance(result, EventStream):
        events = result.events
        async def metered():
            with scope(owner, category, reference):
                try:
                    async for event in events:
                        yield event
                finally:
                    await events.aclose()
        result.events = metered()
    return result
