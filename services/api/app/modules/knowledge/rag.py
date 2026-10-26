"""父子分块向量任务与带权限过滤的检索。"""
import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
from sqlalchemy import delete, func, or_, select
from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from .models import KnowledgeBase, KnowledgeDocument
from .rag_models import KnowledgeParentChunk as Parent, KnowledgeChildChunk as Child
from .repository import KnowledgeRepository
from .schemas import KnowledgeDocumentOut
from .parsing import notify_parse

log = logging.getLogger(__name__)


def invalidate(row):
    """正文变化时使旧索引与在途任务失效。"""
    row.vector_status = "unindexed"
    row.vectorized_at = row.vector_error = row.vector_task_id = row.vector_claim_token = None
    row.vector_profile = row.vector_started_at = row.vector_lease_until = None
    row.vector_done = row.vector_total = row.vector_attempts = 0


async def call_sidecar(path: str, data: dict):
    """通过服务端认证调用分块或向量服务。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise ValueError("请配置 API 与 Sidecar 的内部服务凭证。")
    async with httpx.AsyncClient(timeout=110, follow_redirects=False) as client:
        response = await client.post(config.SIDECAR_API_URL + "/internal/knowledge/" + path,
            headers={"X-Internal-Token": config.SIDECAR_INTERNAL_TOKEN}, json=data)
    if response.status_code != 200:
        message = "向量服务请求失败，请稍后重试。"
        try:
            detail = response.json().get("detail")
            if isinstance(detail, dict) and isinstance(detail.get("message"), str):
                message = detail["message"][:300]
        except (ValueError, AttributeError):
            pass
        raise ValueError(message)
    return response.json()


async def authorize_bases(owner_id: int, base_ids: list[int]):
    """全部知识库均须属于当前用户，不静默扩大检索范围。"""
    if not base_ids:
        raise ApiError(ApiCode.PARAM_ERROR, "请先选择知识库。")
    async with session.read_session() as db:
        found = set((await db.scalars(select(KnowledgeBase.id).where(
            KnowledgeBase.owner_id == owner_id, KnowledgeBase.id.in_(base_ids)))).all())
    if found != set(base_ids):
        raise ApiError(ApiCode.NOT_FOUND, "知识库不存在或无权访问。", 404)


async def enqueue(owner_id: int, base_id: int, document_id: str, expected_parsed_at: datetime):
    """锁定解析版本并幂等提交向量任务。"""
    async with session.transaction() as db:
        if not await KnowledgeRepository(db).owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在。", 404)
        row = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id,
            KnowledgeDocument.knowledge_base_id == base_id).with_for_update())
        if row is None:
            raise ApiError(ApiCode.NOT_FOUND, "文档不存在。", 404)
        if row.parse_status != "parsed" or not (row.parse_content or "").strip():
            raise ApiError(ApiCode.STATE_CONFLICT, "请先解析文档并保存正文。", 409)
        if row.parsed_at != expected_parsed_at:
            raise ApiError(ApiCode.STATE_CONFLICT, "解析正文已更新，请刷新后重试。", 409)
        if row.vector_status in ("queued", "indexing"):
            return KnowledgeDocumentOut.model_validate(row)
        invalidate(row)
        row.vector_task_id = str(uuid4())
        row.vector_status = "queued"
        row.vector_started_at = datetime.now(timezone.utc)
        await db.flush()
        await notify_parse(db, base_id, document_id)
        return KnowledgeDocumentOut.model_validate(row)


async def claim():
    """领取排队或租约过期的向量任务。"""
    async with session.transaction() as db:
        row = await db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.vector_status.in_(["queued", "indexing"]),
            or_(KnowledgeDocument.vector_lease_until.is_(None), KnowledgeDocument.vector_lease_until < func.now()),
        ).order_by(KnowledgeDocument.vector_started_at).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.vector_claim_token = str(uuid4())
        row.vector_lease_until = datetime.now(timezone.utc) + timedelta(seconds=180)
        row.vector_attempts += 1
        row.vector_status = "indexing"
        row.vector_done = 0
        await db.execute(delete(Parent).where(Parent.document_id == row.id))
        await db.flush()
        await notify_parse(db, row.knowledge_base_id, row.id)
        return row


async def locked(db, snapshot):
    """仅当前任务、租约和解析版本可继续写入。"""
    return await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == snapshot.id, KnowledgeDocument.vector_task_id == snapshot.vector_task_id,
        KnowledgeDocument.vector_claim_token == snapshot.vector_claim_token,
        KnowledgeDocument.vector_status == "indexing", KnowledgeDocument.parsed_at == snapshot.parsed_at,
    ).with_for_update())


async def fail(snapshot, message):
    """发布安全错误，保留重试入口。"""
    async with session.transaction() as db:
        row = await locked(db, snapshot)
        if row:
            row.vector_status, row.vector_error = "failed", message[:300]
            row.vector_claim_token = row.vector_lease_until = None
            await db.flush()
            await notify_parse(db, row.knowledge_base_id, row.id)


async def process(snapshot):
    """分批持久化子向量，全部成功后原子发布索引。"""
    try:
        if snapshot.vector_attempts > 3:
            raise ValueError("向量任务多次中断，请重新提交。")
        split = await call_sidecar("chunks", {"content": snapshot.parse_content, "metadata": snapshot.parse_metadata or []})
        parents, children = [], []
        for position, parent in enumerate(split["parents"]):
            parent_id = str(uuid4())
            parents.append(Parent(id=parent_id, document_id=snapshot.id, task_id=snapshot.vector_task_id,
                position=position, content=parent["content"], chunk_metadata=parent["metadata"]))
            for index, child in enumerate(parent["children"]):
                children.append({"id": str(uuid4()), "parent_id": parent_id, "position": index,
                                 "content": child["content"], "start_offset": child["start"]})
        if not children or len(children) > 4096:
            raise ValueError("分块结果为空或超过 4096 个子块。")
        async with session.transaction() as db:
            row = await locked(db, snapshot)
            if row is None:
                return
            db.add_all(parents)
            row.vector_total = len(children)
            row.vector_lease_until = datetime.now(timezone.utc) + timedelta(seconds=180)
        current_profile = None
        for start in range(0, len(children), 16):
            batch = children[start:start + 16]
            result = await call_sidecar("embed", {"texts": [child["content"] for child in batch]})
            vectors = result["vectors"]
            if result.get("dimensions") != 1024 or len(vectors) != len(batch):
                raise ValueError("向量服务返回的数量或维度不匹配。")
            if not isinstance(result.get("profile"), str) or len(result["profile"]) != 64:
                raise ValueError("向量空间标识无效。")
            if current_profile and current_profile != result["profile"]:
                raise ValueError("向量模型配置已变化，请重新向量化。")
            current_profile = result["profile"]
            async with session.transaction() as db:
                row = await locked(db, snapshot)
                if row is None:
                    return
                for child, vector in zip(batch, vectors, strict=True):
                    validate_vector(vector)
                    db.add(Child(**child, embedding=vector))
                row.vector_done = start + len(batch)
                row.vector_lease_until = datetime.now(timezone.utc) + timedelta(seconds=180)
                if row.vector_done == row.vector_total:
                    row.vector_status, row.vector_profile = "indexed", current_profile
                    row.vectorized_at = datetime.now(timezone.utc)
                    row.vector_claim_token = row.vector_lease_until = None
                    row.vector_error = None
                await db.flush()
                await notify_parse(db, row.knowledge_base_id, row.id)
    except asyncio.CancelledError:
        raise
    except ValueError as cause:
        await fail(snapshot, str(cause))
    except (httpx.HTTPError, KeyError, TypeError):
        await fail(snapshot, "向量化连接失败或结果无效，请重试。")
    except Exception:
        log.exception("文档向量化任务异常，document=%s", snapshot.id)
        await fail(snapshot, "向量化失败，请稍后重试。")


def validate_vector(vector):
    """验证查询及入库向量。"""
    if not isinstance(vector, list) or len(vector) != 1024 or not any(vector) or any(
        type(value) not in (int, float) or not math.isfinite(value) for value in vector
    ):
        raise ValueError("向量必须是 1024 维有限非零数值。")


async def search_vector(owner_id: int, base_ids: list[int], vector: list[float], profile: str, top_k: int = 4):
    """在有权限且版本有效的子块中召回，按父块去重返回引用。"""
    await authorize_bases(owner_id, base_ids)
    validate_vector(vector)
    distance = Child.embedding.cosine_distance(vector)
    async with session.read_session() as db:
        # 先按权限和有效文档过滤；聚合父块最佳子块分数，确保结果不会被其他租户的近邻挤占。
        best = select(Parent.id.label("parent_id"), func.min(distance).label("distance")).join(
            Child, Child.parent_id == Parent.id).join(KnowledgeDocument, KnowledgeDocument.id == Parent.document_id).join(
            KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id).where(
            KnowledgeBase.owner_id == owner_id, KnowledgeBase.id.in_(base_ids),
            KnowledgeDocument.parse_status == "parsed", KnowledgeDocument.vector_status == "indexed",
            KnowledgeDocument.vectorized_at.is_not(None), KnowledgeDocument.vector_profile == profile,
            Parent.task_id == KnowledgeDocument.vector_task_id,
        ).group_by(Parent.id).subquery()
        rows = (await db.execute(select(Parent, KnowledgeDocument, KnowledgeBase, best.c.distance).join(
            best, best.c.parent_id == Parent.id).join(KnowledgeDocument, KnowledgeDocument.id == Parent.document_id).join(
            KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id).order_by(best.c.distance, Parent.id).limit(top_k))).all()
        return [{"citation": f"资料{index + 1}", "parent_id": parent.id, "document_id": document.id,
                 "knowledge_base_id": base.id, "knowledge_base": base.name, "title": document.title,
                 "content": parent.content, "score": round(1 - float(distance), 6), "metadata": parent.chunk_metadata,
                 "url": f"/knowledge/server-{base.id}/files/{document.id}"}
                for index, (parent, document, base, distance) in enumerate(rows)]


async def search(owner_id: int, base_ids: list[int], query: str, top_k: int):
    """将问题向量化后进行权限内检索，供独立测试使用。"""
    await authorize_bases(owner_id, base_ids)
    try:
        result = await call_sidecar("embed", {"texts": [query], "query": True})
        return await search_vector(owner_id, base_ids, result["vectors"][0], result["profile"], top_k)
    except (ValueError, httpx.HTTPError, KeyError, TypeError) as cause:
        raise ApiError(ApiCode.INTERNAL_ERROR, str(cause) if isinstance(cause, ValueError) else "知识库检索暂不可用。", 503) from cause


async def worker():
    """持续领取 PostgreSQL 中的向量任务，重启后恢复过期租约。"""
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
            log.exception("向量任务扫描失败")
            await asyncio.sleep(3)


async def index_coverage(owner_id: int, base_ids: list[int], profile: str) -> dict:
    """仅统计索引就绪状态，不读取文档正文。"""
    await authorize_bases(owner_id, base_ids)
    ready = ((KnowledgeDocument.parse_status == "parsed") & (KnowledgeDocument.vector_status == "indexed") &
             KnowledgeDocument.vectorized_at.is_not(None) & (KnowledgeDocument.vector_profile == profile))
    async with session.read_session() as db:
        total, indexed, pending = (await db.execute(select(
            func.count(KnowledgeDocument.id), func.count(KnowledgeDocument.id).filter(ready),
            func.count(KnowledgeDocument.id).filter(KnowledgeDocument.vector_status.in_(["queued", "indexing"])),
        ).join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id).where(
            KnowledgeBase.owner_id == owner_id, KnowledgeBase.id.in_(base_ids)))).one()
        return {"total": total, "ready": indexed, "pending": pending, "not_ready": total - indexed}
