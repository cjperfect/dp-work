"""本地向量索引；SQLite 正文仍是唯一数据源。"""
import asyncio
import httpx
import logging
import math
import sqlite3
import struct

from .. import config
from ..knowledge.rag.embedding import ArkEmbeddings, EmbeddingError, profile
from . import repository as repo

log = logging.getLogger(__name__)


def normalized(vector):
    """归一化并拒绝损坏或无效的向量。"""
    if not vector or any(type(x) not in (float, int) or not math.isfinite(x) for x in vector):
        raise ValueError('无效的记忆向量。')
    length = math.hypot(*vector)
    if not length or not math.isfinite(length):
        raise ValueError('记忆向量不能为空。')
    return [x / length for x in vector]


def cached(owner, rows, space, root=None):
    """只读取当前正文版本及当前模型空间的索引。"""
    with repo.connection(owner, root) as db:
        records = {row['memory_id']: row for row in db.execute(
            'SELECT * FROM memory_vectors WHERE profile=?', (space,))}
    result = {}
    for row in rows:
        entry = records.get(row['id'])
        if entry is None or entry['revision'] != row['revision'] or not 1 <= entry['dimensions'] <= 4096:
            continue
        try:
            result[row['id']] = normalized(struct.unpack('<' + 'f' * entry['dimensions'], entry['vector']))
        except (ValueError, TypeError, struct.error):
            continue
    return result


def store(owner, rows, vectors, space, root=None):
    """提交前校验版本，避免删除或并发修改后写回过期索引。"""
    if len(rows) != len(vectors):
        raise ValueError('向量数量不匹配。')
    prepared = [(row, normalized(vector)) for row, vector in zip(rows, vectors)]
    with repo.connection(owner, root, True) as db:
        for row, vector in prepared:
            current = db.execute('SELECT revision FROM memories WHERE id=?', (row['id'],)).fetchone()
            if current is None or current['revision'] != row['revision']:
                continue
            db.execute('INSERT OR REPLACE INTO memory_vectors VALUES(?,?,?,?,?,?)',
                       (row['id'], row['revision'], space, len(vector),
                        struct.pack('<' + 'f' * len(vector), *vector), repo.timestamp()))


async def index_rows(owner, rows, root=None, embeddings=None):
    """分批补齐旧记忆及修改后的向量，不在数据库事务中调用模型。"""
    space, embeddings = profile(), embeddings or ArkEmbeddings()
    found = await asyncio.to_thread(cached, owner, rows, space, root)
    missing = [row for row in rows if row['id'] not in found]
    for start in range(0, len(missing), 16):
        batch = missing[start:start + 16]
        vectors = await embeddings.aembed_documents([row['title'] + '\n' + row['content'] for row in batch])
        await asyncio.to_thread(store, owner, batch, vectors, space, root)
    return space


async def ranked(owner, rows, query, root=None, embeddings=None):
    """以余弦相似度排序，作用范围已由调用者过滤并去重。"""
    embeddings = embeddings or ArkEmbeddings()
    space = await index_rows(owner, rows, root, embeddings)
    needle = normalized(await embeddings.aembed_query(query[:4000]))
    found = await asyncio.to_thread(cached, owner, rows, space, root)
    scored = []
    for row in rows:
        vector = found.get(row['id'])
        if vector is None or len(vector) != len(needle):
            continue
        score = sum(a * b for a, b in zip(needle, vector))
        if score >= config.MEMORY_MIN_SIMILARITY:
            scored.append((score, row))
    return [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)]


async def backfill(owner, root=None):
    """后台每批最多处理十六条缺失索引，失败留待下次重试。"""
    if not config.EMBEDDING_API_KEY:
        return
    try:
        rows = await asyncio.to_thread(repo.indexable, owner, root)
        if not rows:
            return
        found = await asyncio.to_thread(cached, owner, rows, profile(), root)
        missing = [row for row in rows if row['id'] not in found][:16]
        if missing:
            async with asyncio.timeout(config.MEMORY_RETRIEVAL_TIMEOUT_SECONDS):
                from ..usage.ledger import scope
                with scope(owner, 'embedding'):
                    await index_rows(owner, missing, root)
    except (EmbeddingError, httpx.HTTPError, TimeoutError, ValueError, OSError, sqlite3.DatabaseError, repo.MemoryError):
        log.warning('Memory vector indexing deferred')
