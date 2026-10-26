"""由 PostgreSQL 保存进度的异步文档解析任务。"""
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select, update, text

from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from .models import KnowledgeDocument, KnowledgeBase
from .repository import KnowledgeRepository
from .schemas import KnowledgeDocumentOut
from . import storage

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
        record.parse_status = "queued"
        record.parse_error = record.parse_content = record.parse_metadata = record.parsed_at = None
        record.parse_blocks = record.vectorized_at = None
        record.parse_claim_token = record.parse_lease_until = None
        record.parse_started_at = datetime.now(timezone.utc)
        await db.flush()
        await notify_parse(db, base_id, document_id)
        return KnowledgeDocumentOut.model_validate(record)


async def claim() -> KnowledgeDocument | None:
    """领取到期任务，过期租约可被其他进程恢复。"""
    async with session.transaction() as db:
        row = await db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.parse_status.in_(["queued", "parsing"]),
            or_(KnowledgeDocument.parse_lease_until.is_(None), KnowledgeDocument.parse_lease_until < func.now()),
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
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise ValueError("请先配置 API 和 Sidecar 的 SIDECAR_INTERNAL_TOKEN。")
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
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
        if row.parse_started_at and (datetime.now(timezone.utc) - row.parse_started_at).total_seconds() > config.DOCUMENT_PARSE_TIMEOUT:
            raise ValueError("文档解析超时，请稍后重试。")
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
    except (ValueError, OSError) as cause:
        await finish(row, parse_status="failed", parse_error=str(cause)[:300], parse_lease_until=None)
    except httpx.HTTPError:
        await finish(row, parse_status="failed", parse_error="解析服务连接失败，请稍后重试。", parse_lease_until=None)


async def worker():
    """持续领取任务，关闭时保留数据库中的待处理状态。"""
    while True:
        try:
            row = await claim()
            if row:
                await process(row)
            else:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("文档解析任务执行异常")
            await asyncio.sleep(3)


async def notify_parse(db, base_id: int, document_id: str):
    """事务提交时发布解析状态，通知内容不包含文档正文。"""
    owner = await db.scalar(select(KnowledgeBase.owner_id).where(KnowledgeBase.id == base_id))
    if owner is not None:
        await db.execute(text("SELECT pg_notify('document_parsing', :payload)"), {"payload": json.dumps({
            "owner_id": owner, "base_id": base_id, "document_id": document_id,
        })})


async def parse_states(owner_id: int, document_id: str | None = None) -> list[dict]:
    """读取当前用户的解析任务元数据，供快照与事件推送使用。"""
    statement = select(KnowledgeDocument, KnowledgeBase.owner_id).join(
        KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id
    ).where(KnowledgeBase.owner_id == owner_id, KnowledgeDocument.parse_started_at.is_not(None))
    if document_id is not None:
        statement = statement.where(KnowledgeDocument.id == document_id)
    async with session.read_session() as db:
        rows = (await db.execute(statement)).all()
        return [{"id": row.id, "base_id": row.knowledge_base_id, "owner_id": owner,
                 "name": row.original_name or row.title, "status": row.parse_status,
                 "task_id": row.parse_started_at.isoformat(),
                 "error": row.parse_error, "parsed_at": row.parsed_at.isoformat() if row.parsed_at else None}
                for row, owner in rows]


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
            row.vectorized_at = None
            await db.flush()
        return KnowledgeDocumentOut.model_validate(row)
