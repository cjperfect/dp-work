"""由 PostgreSQL 保存进度的异步文档解析任务。"""
from src.infrastructure.sidecar.transport import client as sidecar_client
from src.infrastructure.sidecar.relay import DeviceOffline
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select, update, text

from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.infrastructure.tasks.outbox import enqueue as enqueue_message
from .models import KnowledgeDocument, KnowledgeBase
from .repository import KnowledgeRepository
from .schemas import KnowledgeDocumentOut
from .search_models import KnowledgeSearchSync as SearchSync
from . import storage
from .search_index import enqueue as enqueue_search

logger = logging.getLogger(__name__)


async def request_parse(owner_id: int, base_id: int, document_id: str) -> KnowledgeDocumentOut:
    """校验权限并幂等提交解析，失败任务可重试。"""
    async with session.transaction() as db:
        if not await KnowledgeRepository(db).owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        record = await db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id, KnowledgeDocument.knowledge_base_id == base_id
        ).with_for_update())
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "文档不存在", 404)
        if record.parse_status in ("queued", "parsing", "parsed"):
            return KnowledgeDocumentOut.model_validate(record)
        if record.file_type not in ("pdf", "txt", "md", "docx"):
            raise ApiError(ApiCode.PARAM_ERROR, "当前支持 TXT、Markdown、PDF 和 DOCX，旧版 DOC 暂不支持。", 400)
        from .rag import invalidate
        if record.vector_task_id or record.vectorized_at:
            await enqueue_search(db, record.id)
        invalidate(record)
        record.parse_status = "queued"
        record.parse_error = record.parse_content = record.parse_metadata = record.parsed_at = None
        record.parse_blocks = record.vectorized_at = None
        record.parse_claim_token = record.parse_lease_until = None
        record.parse_started_at = datetime.now(timezone.utc)
        await enqueue_message(db, "parse", record.id, record.parse_started_at.isoformat())
        await db.flush()
        await notify_parse(db, base_id, document_id)
        return KnowledgeDocumentOut.model_validate(record)


async def claim(document_id=None, version=None) -> KnowledgeDocument | None:
    """领取到期任务，过期租约可被其他进程恢复。"""
    async with session.transaction() as db:
        row = await db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.parse_status.in_(["queued", "parsing"]),
            or_(KnowledgeDocument.parse_lease_until.is_(None), KnowledgeDocument.parse_lease_until < func.now()),
            *([KnowledgeDocument.id == document_id] if document_id is not None else []),
            *([KnowledgeDocument.parse_started_at == datetime.fromisoformat(version)] if version is not None else []),
        ).order_by(KnowledgeDocument.parse_started_at).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.parse_claim_token = str(uuid4())
        row.parse_lease_until = datetime.now(timezone.utc) + timedelta(seconds=180)
        row.parse_status = "parsing"
        await db.flush()
        await notify_parse(db, row.knowledge_base_id, row.id)
        return row


async def finish(row: KnowledgeDocument, **values) -> bool:
    """只有当前租约且文档未被修改时才写回结果。"""
    async with session.transaction() as db:
        statement = update(KnowledgeDocument).where(
            KnowledgeDocument.id == row.id, KnowledgeDocument.parse_claim_token == row.parse_claim_token,
            KnowledgeDocument.parse_status == "parsing",
        ).values(**values, parse_claim_token=None).returning(KnowledgeDocument.id)
        changed = await db.scalar(statement) is not None
        if changed:
            await notify_parse(db, row.knowledge_base_id, row.id)
        return changed


async def sidecar(method: str, path: str, **kwargs) -> dict:
    """通过内部认证调用 Sidecar，限制调用时长。"""
    if config.SIDECAR_TRANSPORT != "device" and not config.SIDECAR_INTERNAL_TOKEN:
        raise ValueError("请先配置 API 和 Sidecar 的 SIDECAR_INTERNAL_TOKEN。")
    async with sidecar_client(timeout=min(120, config.DOCUMENT_PARSE_TIMEOUT)) as client:
        response = await client.request(method, config.SIDECAR_API_URL + "/internal/knowledge/parse" + path,
                                        headers={"X-Internal-Token": config.SIDECAR_INTERNAL_TOKEN}, **kwargs)
        if response.status_code != 200:
            message = "文档解析服务暂时不可用，请稍后重试。"
            try:
                detail = response.json().get("detail")
                if isinstance(detail, dict) and isinstance(detail.get("message"), str):
                    message = detail["message"][:300]
            except ValueError:
                pass
            raise ValueError(message)
        return response.json()


async def process(row: KnowledgeDocument):
    """调用 Sidecar 解析，网络等待不占用数据库事务。"""
    try:
        if row.file_type not in ("pdf", "txt", "md", "docx"):
            raise ValueError("当前支持 TXT、Markdown、PDF 和 DOCX 解析。")
        if row.source == "editor":
            content = row.content.encode("utf-8")
        elif row.storage_key:
            content = await asyncio.to_thread(storage.file_path(row.storage_key).read_bytes)
        else:
            raise ValueError("源文件不存在，请重新上传。")
        if len(content) > storage.MAX_FILE_SIZE:
            raise ValueError("文件不能超过 20 MB。")
        result = await sidecar("POST", "", content=content, params={"file_type": row.file_type})
        if result.get("status") == "parsed" and isinstance(result.get("content"), str) and result["content"].strip():
            await finish(row, parse_status="parsed", parse_content=result["content"],
                         parse_metadata=result.get("metadata", []), parse_blocks=result.get("blocks"), vectorized_at=None, parsed_at=datetime.now(timezone.utc),
                         parse_error=None, parse_lease_until=None)
        else:
            raise ValueError("解析服务返回了无效的正文。")
    except asyncio.CancelledError:
        raise
    except DeviceOffline:
        raise
    except (ValueError, OSError) as cause:
        await finish(row, parse_status="failed", parse_error=str(cause)[:300], parse_lease_until=None)
    except httpx.HTTPError:
        await finish(row, parse_status="failed", parse_error="解析服务连接失败，请稍后重试。", parse_lease_until=None)


async def notify_parse(db, base_id: int, document_id: str):
    """事务提交时发布解析状态，通知内容不包含文档正文。"""
    owner = await db.scalar(select(KnowledgeBase.owner_id).where(KnowledgeBase.id == base_id))
    if owner is not None:
        await db.execute(text("SELECT pg_notify('document_parsing', :payload)"), {"payload": json.dumps({
            "owner_id": owner, "base_id": base_id, "document_id": document_id,
        })})


async def parse_states(owner_id: int, document_id: str | None = None) -> list[dict]:
    """读取当前用户的解析任务元数据，供快照与事件推送使用。"""
    statement = select(KnowledgeDocument, KnowledgeBase.owner_id, SearchSync).join(
        KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id
    ).outerjoin(SearchSync, SearchSync.document_id == KnowledgeDocument.id).where(KnowledgeBase.owner_id == owner_id)
    if document_id is not None:
        statement = statement.where(KnowledgeDocument.id == document_id)
    else:
        statement = statement.where(or_(KnowledgeDocument.parse_started_at.is_not(None), KnowledgeDocument.vector_task_id.is_not(None)))
    async with session.read_session() as db:
        rows = (await db.execute(statement)).all()
        return [{"id": row.id, "base_id": row.knowledge_base_id, "owner_id": owner,
                 "name": row.original_name or row.title, "status": row.parse_status,
                 "task_id": row.parse_started_at.isoformat() if row.parse_started_at else "",
                 "error": row.parse_error, "parsed_at": row.parsed_at.isoformat() if row.parsed_at else None,
                 "vector_status": row.vector_status, "vector_task_id": row.vector_task_id, "vector_error": row.vector_error,
                 "vector_done": row.vector_done, "vector_total": row.vector_total,
                 "vectorized_at": row.vectorized_at.isoformat() if row.vectorized_at else None,
                 "search_task_id": str(sync.revision) if sync and sync.desired_task_id == row.vector_task_id and sync.desired_task_id else None,
                 "search_status": ("synced" if sync.synced_revision == sync.revision else "syncing")
                     if sync and sync.desired_task_id and sync.desired_task_id == row.vector_task_id and row.vector_status == "indexed" else None}
                for row, owner, sync in rows]


async def save_parsed(owner_id: int, base_id: int, document_id: str, body) -> KnowledgeDocumentOut:
    """保存解析正文，保留源文件并防止覆盖他人的新修改。"""
    async with session.transaction() as db:
        if not await KnowledgeRepository(db).owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        row = await db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id, KnowledgeDocument.knowledge_base_id == base_id
        ).with_for_update())
        if row is None:
            raise ApiError(ApiCode.NOT_FOUND, "文档不存在", 404)
        if row.parse_status != "parsed":
            raise ApiError(ApiCode.STATE_CONFLICT, "请先完成文档解析。", 409)
        if row.parsed_at != body.expected_parsed_at:
            raise ApiError(ApiCode.STATE_CONFLICT, "解析文档已在其他页面更新，请刷新后重试。", 409)
        if row.parse_content != body.content or row.parse_blocks != body.blocks:
            row.parse_content, row.parse_blocks = body.content, body.blocks
            row.parsed_at = datetime.now(timezone.utc)
            from .rag import invalidate
            had_index = row.vector_status != "unindexed"
            invalidate(row)
            await db.flush()
            if had_index:
                await enqueue_search(db, row.id)
                await notify_parse(db, base_id, document_id)
        return KnowledgeDocumentOut.model_validate(row)
