"""子块两路召回、RRF 融合及父块去重，PG 最终校验权限与版本。"""
import asyncio
import math
from collections import defaultdict
from sqlalchemy import select
from src.core import config
from src.infrastructure.database import session
from .models import KnowledgeBase as Base, KnowledgeDocument as Document
from .rag_models import KnowledgeParentChunk as Parent, KnowledgeChildChunk as Child
from .search_models import KnowledgeSearchSync as Sync
from .search_client import SearchClient, SearchError


def active_scope(owner_id, base_ids, profile=None):
    """所有召回与最终读取复用同一权限、版本边界。"""
    conditions = [Base.owner_id == owner_id, Base.id.in_(base_ids), Document.parse_status == "parsed",
        Document.vector_status == "indexed", Document.vectorized_at.is_not(None), Parent.task_id == Document.vector_task_id]
    if profile is not None:
        conditions.append(Document.vector_profile == profile)
    return conditions


def fuse_ranks(vector_hits, keyword_hits, constant=60):
    """按子块 ID 做 RRF，不直接相加不同尺度的原始分数。"""
    scores, channels, raw = defaultdict(float), defaultdict(set), defaultdict(dict)
    for channel, hits in (("vector", vector_hits), ("keyword", keyword_hits)):
        seen = set()
        for rank, hit in enumerate(hits, 1):
            key = hit["child_id"]
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1 / (constant + rank)
            channels[key].add(channel)
            raw[key][channel] = hit["score"]
    return [{"child_id": key, "score": score, "channels": sorted(channels[key]), "raw": raw[key]}
        for key, score in sorted(scores.items(), key=lambda row: (-row[1], row[0]))]


async def vector_candidates(owner_id, base_ids, vector, profile, limit):
    """pgvector 只在权限内、当前发布的子块中召回。"""
    distance = Child.embedding.cosine_distance(vector)
    async with session.read_session() as db:
        rows = (await db.execute(select(Child.id, distance).join(Parent, Parent.id == Child.parent_id).join(
            Document, Document.id == Parent.document_id).join(Base, Base.id == Document.knowledge_base_id).where(
            *active_scope(owner_id, base_ids, profile)).order_by(distance, Child.id).limit(limit))).all()
        return [{"child_id": child_id, "score": 1 - float(score)} for child_id, score in rows]


async def keyword_candidates(owner_id, base_ids, query, limit):
    """ES 查询前传入有效任务范围，查询后再次按 PG 校验子块。"""
    async with session.read_session() as db:
        records = (await db.execute(select(Document.vector_task_id, Sync.revision, Sync.synced_revision,
            Sync.desired_task_id).join(Base, Base.id == Document.knowledge_base_id).outerjoin(Sync, Sync.document_id == Document.id).where(
            Base.owner_id == owner_id, Base.id.in_(base_ids), Document.parse_status == "parsed",
            Document.vector_status == "indexed", Document.vectorized_at.is_not(None)))).all()
    tasks = [task for task, *_ in records if task]
    pending = sum(revision is None or revision != synced or desired != task for task, revision, synced, desired in records)
    hits = await SearchClient().search(owner_id, base_ids, tasks, query, limit)
    if hits:
        async with session.read_session() as db:
            valid = set((await db.scalars(select(Child.id).join(Parent, Parent.id == Child.parent_id).join(
                Document, Document.id == Parent.document_id).join(Base, Base.id == Document.knowledge_base_id).where(
                Child.id.in_([hit["child_id"] for hit in hits]), *active_scope(owner_id, base_ids)))).all())
        hits = [hit for hit in hits if hit["child_id"] in valid]
    return hits, pending, len(records)


async def search(owner_id, base_ids, query, vector, profile, top_k):
    """并行执行两路召回，任何一条可用时继续提供结果。"""
    if vector is not None and (not isinstance(vector, list) or len(vector) != 1024 or not any(vector) or any(
        type(value) not in (int, float) or not math.isfinite(value) for value in vector)):
        raise SearchError("检索向量必须为 1024 维有限非零数值。")
    limit = max(top_k, min(200, max(10, config.RAG_HYBRID_CANDIDATES)))
    dense_enabled = vector is not None and profile is not None
    keyword_enabled = config.ELASTICSEARCH_ENABLED and bool(query.strip())
    async def no_dense():
        return []
    async def no_keyword():
        return [], 0, 0
    dense, lexical = await asyncio.gather(
        vector_candidates(owner_id, base_ids, vector, profile, limit) if dense_enabled else no_dense(),
        keyword_candidates(owner_id, base_ids, query, limit) if keyword_enabled else no_keyword(), return_exceptions=True)
    dense_ok = dense_enabled and not isinstance(dense, Exception)
    lexical_ok = keyword_enabled and not isinstance(lexical, Exception)
    if not dense_ok and not lexical_ok:
        raise SearchError("语义与关键词检索均不可用，请检查向量和 Elasticsearch 服务。")
    vector_hits = dense if dense_ok else []
    keyword_hits, pending, total = lexical if lexical_ok else ([], 0, 0)
    messages = []
    if keyword_enabled and not lexical_ok:
        messages.append("关键词服务暂不可用，本次使用语义检索。")
    if not dense_ok:
        messages.append("语义服务暂不可用，本次使用关键词检索。")
    if pending:
        messages.append("部分文档的关键词索引仍在同步。")
    effective_lexical = lexical_ok and (pending < total or bool(keyword_hits) or total == 0)
    mode = "hybrid" if dense_ok and effective_lexical else "vector" if dense_ok else "keyword"
    ranked = fuse_ranks(vector_hits, keyword_hits, max(1, config.RAG_RRF_CONSTANT))
    if not ranked:
        return {"sources": [], "retrieval": {"mode": mode, "keyword_pending": pending}, "message": "".join(messages)}
    ids = [row["child_id"] for row in ranked]
    async with session.read_session() as db:
        rows = (await db.execute(select(Child.id, Parent, Document.title, Document.id, Base.id, Base.name).join(
            Parent, Parent.id == Child.parent_id).join(Document, Document.id == Parent.document_id).join(
            Base, Base.id == Document.knowledge_base_id).where(Child.id.in_(ids), *active_scope(owner_id, base_ids)))).all()
        candidates = {child_id: (parent, title, document_id, base_id, base_name) for child_id, parent, title, document_id, base_id, base_name in rows}
        sources, parents_seen = [], set()
        for hit in ranked:
            record = candidates.get(hit["child_id"])
            if record is None:
                continue
            parent, title, document_id, base_id, base_name = record
            if parent.id in parents_seen:
                continue
            parents_seen.add(parent.id)
            sources.append({"citation": f"资料{len(sources) + 1}", "parent_id": parent.id, "document_id": document_id,
                "knowledge_base_id": base_id, "knowledge_base": base_name, "title": title, "content": parent.content,
                "metadata": parent.chunk_metadata, "url": f"/knowledge/server-{base_id}/files/{document_id}",
                "score": hit["score"], "score_type": "rrf", "retrieval_mode": mode, "retrieval_channels": hit["channels"],
                "vector_score": hit["raw"].get("vector"), "keyword_score": hit["raw"].get("keyword")})
            if len(sources) == top_k:
                break
    return {"sources": sources, "retrieval": {"mode": mode, "keyword_pending": pending}, "message": "".join(messages)}
