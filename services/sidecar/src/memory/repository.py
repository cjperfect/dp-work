"""SQLite 是记忆正文的数据源，与聊天事件和向量索引分离。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
import unicodedata
from uuid import uuid4

from .. import config

LOCK = threading.RLock()


class MemoryError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def memory_file(owner, root=None):
    """账号由 Main 注入，不能用请求正文切换存储目录。"""
    if type(owner) is not int or owner <= 0:
        raise MemoryError('用户身份无效。', 400)
    return Path(root or config.DATA_ROOT) / 'memories' / str(owner) / 'memory.sqlite3'


@contextmanager
def connection(owner, root=None, write=False):
    file = memory_file(owner, root)
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if file.parent.is_symlink() or file.is_symlink():
        raise MemoryError('记忆存储目录不能使用软链接。')
    os.chmod(file.parent, 0o700)
    db = sqlite3.connect(file, timeout=10)
    db.row_factory = sqlite3.Row
    LOCK.acquire()
    try:
        os.chmod(file, 0o600)
        db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            PRAGMA foreign_keys=ON;
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, memory_key TEXT NOT NULL,
                content TEXT NOT NULL, kind TEXT NOT NULL, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
                enabled INTEGER NOT NULL, revision INTEGER NOT NULL, source TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT,
                UNIQUE(scope,scope_id,memory_key));
            CREATE TABLE IF NOT EXISTS memory_vectors (
                memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, profile TEXT NOT NULL, dimensions INTEGER NOT NULL,
                vector BLOB NOT NULL, updated_at TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS invalidate_memory_vector AFTER UPDATE ON memories
                BEGIN DELETE FROM memory_vectors WHERE memory_id=NEW.id; END;
            CREATE TABLE IF NOT EXISTS memory_revisions (
                memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(memory_id,revision));
            CREATE TABLE IF NOT EXISTS memory_tombstones (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, deleted_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL, revision INTEGER NOT NULL);
            INSERT OR IGNORE INTO preferences(id,enabled,revision) VALUES(1,1,1);
            CREATE INDEX IF NOT EXISTS memory_scope ON memories(scope,scope_id,enabled);
            CREATE TABLE IF NOT EXISTS memory_jobs (
                thread_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL, retry_at REAL NOT NULL, lease_until REAL NOT NULL,
                token TEXT NOT NULL, error_code TEXT, updated_at TEXT NOT NULL,
                source_updated TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS memory_inputs (
                thread_id TEXT NOT NULL, message_id TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(thread_id,message_id));
            CREATE TABLE IF NOT EXISTS memory_origins (
                memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                thread_id TEXT NOT NULL, fingerprint TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(memory_id,thread_id));
            CREATE TABLE IF NOT EXISTS memory_exclusions (
                scope TEXT NOT NULL, scope_id TEXT NOT NULL, key_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL, forgotten_at TEXT NOT NULL,
                PRIMARY KEY(scope,scope_id,key_hash));
            PRAGMA user_version=1;
        ''')
        db.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in db.execute('PRAGMA table_info(preferences)')}
        for name, definition in (('auto_generate', 'INTEGER NOT NULL DEFAULT 1'),
                                 ('generation_epoch', 'INTEGER NOT NULL DEFAULT 1'),
                                 ('forget_before', "TEXT NOT NULL DEFAULT ''")):
            if name not in columns:
                db.execute(f'ALTER TABLE preferences ADD COLUMN {name} {definition}')
        if 'source_updated' not in {row[1] for row in db.execute('PRAGMA table_info(memory_jobs)')}:
            db.execute("ALTER TABLE memory_jobs ADD COLUMN source_updated TEXT NOT NULL DEFAULT ''")
        db.commit()
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        if db.in_transaction:
            db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
        LOCK.release()


def outward(row):
    value = dict(row)
    scope_id = value.pop('scope_id')
    value.pop('memory_key')
    return {**value, 'enabled': bool(value['enabled']),
            'agent_code': scope_id if value['scope'] == 'agent' else None,
            'project_id': scope_id if value['scope'] == 'project' else None}


def key_for(title):
    return ' '.join(unicodedata.normalize('NFKC', title).casefold().split())


def list_memories(owner, query, root=None):
    """按作用范围及关键词分页查询精选记忆。"""
    where, args = [], []
    if query.q.strip():
        term = query.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
        args += ['%' + term + '%'] * 2
    for column in ('scope', 'kind'):
        if getattr(query, column):
            where.append(column + '=?')
            args.append(getattr(query, column))
    if query.agent_code:
        where.append("scope='agent' AND scope_id=?")
        args.append(query.agent_code)
    if query.project_id:
        where.append("scope='project' AND scope_id=?")
        args.append(str(query.project_id))
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    with connection(owner, root) as db:
        total = db.execute('SELECT COUNT(*) FROM memories' + clause, args).fetchone()[0]
        rows = db.execute('SELECT * FROM memories' + clause + ' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?',
                          [*args, query.page_size, (query.page - 1) * query.page_size]).fetchall()
    return {'item': [outward(row) for row in rows], 'page': query.page, 'page_size': query.page_size, 'total': total}


def save(owner, body, key=None, root=None):
    """同名同范围去重，以版本号防止覆盖其他窗口的编辑。"""
    scope_id = body.agent_code if body.scope == 'agent' else str(body.project_id) if body.scope == 'project' else ''
    now, identifier = timestamp(), key or str(uuid4())
    with connection(owner, root, True) as db:
        old = db.execute('SELECT * FROM memories WHERE id=?', (identifier,)).fetchone()
        if key and not old:
            raise MemoryError('记忆不存在或已删除。', 404)
        if old and old['revision'] != body.expected_revision:
            raise MemoryError('记忆已在其他窗口修改，请重新加载后编辑。')
        if not old and db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] >= 1000:
            raise MemoryError('记忆已达 1000 条，请先整理不再适用的信息。')
        values = (body.title, key_for(body.title), body.content, body.kind, body.scope, scope_id,
                  int(body.enabled), old['revision'] + 1 if old else 1, 'manual',
                  old['created_at'] if old else now, now, body.expires_at.isoformat() if body.expires_at else None, identifier)
        try:
            if old:
                db.execute('UPDATE memories SET title=?,memory_key=?,content=?,kind=?,scope=?,scope_id=?,enabled=?,revision=?,source=?,created_at=?,updated_at=?,expires_at=? WHERE id=?', values)
            else:
                db.execute('INSERT INTO memories(title,memory_key,content,kind,scope,scope_id,enabled,revision,source,created_at,updated_at,expires_at,id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', values)
        except sqlite3.IntegrityError as cause:
            raise MemoryError('此范围已存在同名记忆，请编辑原记录。') from cause
        row = db.execute('SELECT * FROM memories WHERE id=?', (identifier,)).fetchone()
        result = outward(row)
        db.execute('INSERT INTO memory_revisions VALUES(?,?,?,?)', (identifier, result['revision'], json.dumps(result, ensure_ascii=False), now))
        db.execute('UPDATE preferences SET generation_epoch=generation_epoch+1 WHERE id=1')
        return result


def remove(owner, key, revision, root=None):
    """遗忘时清除正文和历史版本，保留无正文的删除标记。"""
    with connection(owner, root, True) as db:
        row = db.execute('SELECT * FROM memories WHERE id=?', (key,)).fetchone()
        if not row:
            raise MemoryError('记忆不存在或已删除。', 404)
        if row['revision'] != revision:
            raise MemoryError('记忆已被修改，请重新加载后删除。')
        db.execute('INSERT INTO memory_tombstones VALUES(?,?,?)', (key, revision, timestamp()))
        from .pipeline import digest
        db.execute('INSERT OR REPLACE INTO memory_exclusions VALUES(?,?,?,?,?)',
                   (row['scope'], row['scope_id'], digest(row['memory_key']), digest(key_for(row['content'])), timestamp()))
        # 删除后不再从此前的聊天补提取，避免换标题后又记回同一事实。
        db.execute('UPDATE preferences SET generation_epoch=generation_epoch+1,forget_before=? WHERE id=1', (timestamp(),))
        db.execute('DELETE FROM memories WHERE id=?', (key,))


def preferences(owner, body=None, root=None):
    """独立控制后续运行是否加载长期记忆。"""
    with connection(owner, root, body is not None) as db:
        current = dict(db.execute('SELECT enabled,auto_generate,revision FROM preferences WHERE id=1').fetchone())
        if body is not None:
            if current['revision'] != body.expected_revision:
                raise MemoryError('记忆开关已在其他窗口修改，请重新加载。')
            db.execute('UPDATE preferences SET enabled=?,auto_generate=?,revision=revision+1,generation_epoch=generation_epoch+1 WHERE id=1',
                       (int(body.enabled if body.enabled is not None else current['enabled']),
                        int(body.auto_generate if body.auto_generate is not None else current['auto_generate'])))
            if body.auto_generate is True and not current['auto_generate']:
                db.execute("UPDATE memory_jobs SET attempts=0,retry_at=0 WHERE status='retry'")
            current = dict(db.execute('SELECT enabled,auto_generate,revision FROM preferences WHERE id=1').fetchone())
        return {**current, 'enabled': bool(current['enabled']), 'auto_generate': bool(current['auto_generate'])}


def relevant(owner, agent_code, project_id, root=None):
    """只读取当前账号、Agent 和项目中启用且未过期的记忆。"""
    if not memory_file(owner, root).exists():
        return []
    with connection(owner, root) as db:
        if not db.execute('SELECT enabled FROM preferences WHERE id=1').fetchone()[0]:
            return []
        rows = db.execute('''SELECT * FROM memories WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?) AND
            (scope='user' OR (scope='agent' AND scope_id=?) OR (scope='project' AND scope_id=?))
            ORDER BY CASE scope WHEN 'project' THEN 0 WHEN 'agent' THEN 1 ELSE 2 END,updated_at DESC,id''',
            (timestamp(), agent_code, str(project_id) if project_id else '')).fetchall()
        return [dict(row) for row in rows]


def indexable(owner, root=None):
    """后台索引只读取启用且未过期的记忆。"""
    if not memory_file(owner, root).exists():
        return []
    with connection(owner, root) as db:
        if not db.execute('SELECT enabled FROM preferences WHERE id=1').fetchone()[0]:
            return []
        return [dict(row) for row in db.execute(
            'SELECT * FROM memories WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC,id',
            (timestamp(),))]
