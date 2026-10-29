"""手动管理关键信息，并在新一轮执行前装配适用记忆。"""
import asyncio
import httpx
import logging
import json
import sqlite3
from uuid import UUID

from . import repository as repo
from .schemas import MemoryWrite, MemoryUpdate, MemoryDelete, MemoryQuery, MemoryPreference


def operation(action, owner, body, key=None):
    """路由不能传入任意账号目录或假冒自动提取来源。"""
    if action == 'list':
        return repo.list_memories(owner, MemoryQuery.model_validate(body))
    if action == 'preferences':
        return repo.preferences(owner)
    if action == 'preferences.update':
        return repo.preferences(owner, MemoryPreference.model_validate(body))
    if action in ('update', 'delete'):
        key = str(UUID(key))
    if action == 'delete':
        repo.remove(owner, key, MemoryDelete.model_validate(body).expected_revision)
        return None
    if action in ('create', 'update'):
        data = (MemoryUpdate if action == 'update' else MemoryWrite).model_validate(body)
        if data.scope == 'project':
            from ..sessions.projects import get
            get(owner, str(data.project_id))
        return repo.save(owner, data, key if action == 'update' else None)
    raise repo.MemoryError('不支持的记忆操作。', 400)


def recall(owner, agent_code, project_id, budget=5000, root=None):
    """按范围优先级加载少量事实，不存储对话或推测用户偏好。"""
    if not owner or budget < 100:
        return {'context': '', 'sources': []}
    budget = min(5000, budget)
    try:
        candidates = repo.relevant(owner, agent_code, project_id, root)
    except (sqlite3.DatabaseError, OSError) as cause:
        raise repo.MemoryError('无法读取本机记忆，请检查存储文件或从备份恢复。') from cause
    return pack(candidates, budget)


def unique(candidates):
    """同名记忆先按项目、Agent、用户优先级去重。"""
    seen, selected = set(), []
    for row in candidates:
        if row['memory_key'] not in seen:
            seen.add(row['memory_key'])
            selected.append(row)
    return selected


def pack(candidates, budget):
    """限制注入条数和字符预算，仅暴露必要的来源元数据。"""
    selected = []
    for row in unique(candidates):
        item = {key: row[key] for key in ('id', 'title', 'content', 'kind', 'scope', 'revision')}
        if len(json.dumps([*selected, item], ensure_ascii=False)) <= min(5000, budget):
            selected.append(item)
        if len(selected) >= 8:
            break
    return {'context': json.dumps(selected, ensure_ascii=False) if selected else '',
            'sources': [{key: row[key] for key in ('id', 'title', 'kind', 'scope', 'revision')} for row in selected]}


async def semantic_recall(owner, agent_code, project_id, query, budget=5000, root=None, embeddings=None):
    """按当前问题召回；模型故障回退，删除、过期及作用域变更即时生效。"""
    from .. import config
    from ..knowledge.rag.embedding import EmbeddingError
    from .vectors import ranked
    if not owner or budget < 100:
        return {'context': '', 'sources': []}
    candidates = unique(await asyncio.to_thread(repo.relevant, owner, agent_code, project_id, root))
    if not candidates:
        return pack([], budget)
    try:
        if not query.strip():
            return pack(candidates, budget)
        async with asyncio.timeout(config.MEMORY_RETRIEVAL_TIMEOUT_SECONDS):
            ranked_rows = await ranked(owner, candidates, query, root, embeddings)
        # 向量请求期间可能发生修改、删除、停用或范围变更，不注入旧快照。
        latest = unique(await asyncio.to_thread(repo.relevant, owner, agent_code, project_id, root))
        valid = {(row['id'], row['revision']): row for row in latest}
        return pack([valid[row['id'], row['revision']] for row in ranked_rows
                     if (row['id'], row['revision']) in valid], budget)
    except (EmbeddingError, httpx.HTTPError, TimeoutError, ValueError, OSError):
        logging.getLogger(__name__).warning('Memory semantic retrieval unavailable; using scoped facts')
        return await asyncio.to_thread(recall, owner, agent_code, project_id, budget, root)
