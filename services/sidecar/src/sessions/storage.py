"""JSONL 为持久事件源，SQLite 为可重建的会话投影。"""
import copy
import json
import os
import re
import sqlite3
import threading
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from .. import config


class SessionError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class SessionStorage:
    """一个进程内串行写入；JSONL 落盘后才提交 SQLite 投影。"""
    def __init__(self, root=None):
        self.root = Path(root) if root else config.DATA_ROOT
        self.lock = threading.RLock()

    def paths(self, owner):
        if type(owner) is not int or owner <= 0:
            raise SessionError('用户身份无效。', 400)
        base = self.root / 'data' / 'users' / str(owner)
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(base, 0o700)
        logs = self.root / 'sessions' / str(owner)
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(logs, 0o700)
        memories = self.root / 'memories' / str(owner)
        memories.mkdir(parents=True, exist_ok=True, mode=0o700)
        return base / 'state.sqlite3', logs

    def connect(self, owner):
        file, _ = self.paths(owner)
        db = sqlite3.connect(file, timeout=10)
        os.chmod(file, 0o600)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at TEXT NOT NULL,
                has_history INTEGER NOT NULL, deleted INTEGER NOT NULL, metadata_json TEXT NOT NULL, state_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS thread_items (
                thread_id TEXT NOT NULL, item_id TEXT NOT NULL, parent_id TEXT, item_json TEXT NOT NULL,
                PRIMARY KEY(thread_id,item_id));
            CREATE TABLE IF NOT EXISTS thread_turns (
                thread_id TEXT NOT NULL, run_id TEXT PRIMARY KEY, status TEXT NOT NULL, run_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS thread_history_projection_state (
                thread_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, byte_offset INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS thread_recency ON threads(deleted,has_history,updated_at DESC);
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, deleted INTEGER NOT NULL, data_json TEXT NOT NULL);
            PRAGMA user_version=1;
        ''')
        return db

    @staticmethod
    def valid_key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', key):
            raise SessionError('会话 ID 无效。', 400)
        return key

    def _project(self, db, key, state, ordinal, byte_offset):
        thread = state['thread']
        history = any(m['role'] == 'user' for m in state['nodes'].values()) and any(
            m['role'] == 'assistant' and m['status'] == 'complete' and m['content'].strip() for m in state['nodes'].values())
        thread['has_history'] = bool(history)
        db.execute('INSERT OR REPLACE INTO threads VALUES (?,?,?,?,?,?,?)',
                   (key, thread['title'], thread['updated_at'], history, state.get('deleted', False), encode({**thread, 'draft': ''}), encode(state)))
        items = {row[0]: row[1] for row in db.execute('SELECT item_id,item_json FROM thread_items WHERE thread_id=?', (key,))}
        for mid, message in state['nodes'].items():
            value = encode(message)
            if items.pop(mid, None) != value:
                db.execute('INSERT OR REPLACE INTO thread_items VALUES (?,?,?,?)', (key, mid, message.get('parentId'), value))
        db.executemany('DELETE FROM thread_items WHERE thread_id=? AND item_id=?', [(key, mid) for mid in items])
        turns = {row[0]: row[1] for row in db.execute('SELECT run_id,run_json FROM thread_turns WHERE thread_id=?', (key,))}
        for rid, run in state['runs'].items():
            value = encode(run)
            if turns.pop(rid, None) != value:
                db.execute('INSERT OR REPLACE INTO thread_turns VALUES (?,?,?,?)', (key, rid, run['status'], value))
        db.executemany('DELETE FROM thread_turns WHERE thread_id=? AND run_id=?', [(key, rid) for rid in turns])
        db.execute('INSERT OR REPLACE INTO thread_history_projection_state VALUES (?,?,?)', (key, ordinal, byte_offset))

    @staticmethod
    def _apply(state, patch):
        state.update(patch.get('fields', {}))
        for name, change in patch.get('maps', {}).items():
            target = state.setdefault(name, {})
            target.update(change.get('set', {}))
            for key in change.get('delete', []):
                target.pop(key, None)
        return state

    def _recover(self, db, logs):
        """重放 SQLite 尚未提交的事件；只截断崩溃产生的不完整末行。"""
        for file in sorted(logs.glob('*.jsonl')):
            key = self.valid_key(file.stem)
            row = db.execute('SELECT ordinal,byte_offset FROM thread_history_projection_state WHERE thread_id=?', (key,)).fetchone()
            applied = row[0] if row else 0
            offset = row[1] if row else 0
            if row and file.stat().st_size == offset:
                continue
            row = db.execute('SELECT state_json FROM threads WHERE id=?', (key,)).fetchone()
            state = json.loads(row[0]) if row else {}
            # 删除压缩在原子替换后可能尚未来得及提交新的 SQLite 游标。
            if state.get('deleted'):
                with file.open('rb') as source:
                    try:
                        first = json.loads(source.readline())
                    except ValueError:
                        first = {}
                if first.get('type') == 'session_tombstone' and first.get('ordinal') == 1:
                    state, applied, offset = {}, 0, 0
            ordinal, dirty = applied, False
            with file.open('rb+') as source:
                if file.stat().st_size < offset:
                    raise SessionError('会话日志被截断，请从备份恢复。', 500)
                source.seek(offset)
                while True:
                    start = source.tell()
                    line = source.readline()
                    if not line:
                        break
                    if not line.endswith(b'\n'):
                        source.truncate(start)
                        source.flush()
                        os.fsync(source.fileno())
                        break
                    try:
                        event = json.loads(line)
                        if event['schema_version'] != 1 or event['ordinal'] != ordinal + 1 or event['session_id'] != key:
                            raise ValueError('invalid event sequence')
                        ordinal += 1
                        if ordinal > applied:
                            self._apply(state, event['patch'])
                            dirty = True
                        offset = source.tell()
                    except (ValueError, KeyError, TypeError) as cause:
                        raise SessionError('会话事件日志损坏，请从备份恢复。', 500) from cause
            if ordinal < applied:
                raise SessionError('会话日志与索引不一致，请从备份恢复。', 500)
            if dirty:
                self._project(db, key, state, ordinal, offset)

    def _open(self, owner):
        db = self.connect(owner)
        # 每次打开重放尾部，覆盖“JSONL 成功、SQLite 失败”后的同进程重试。
        try:
            db.execute('BEGIN IMMEDIATE')
            self._recover(db, self.paths(owner)[1])
        except BaseException:
            db.close()
            raise
        return db

    def list(self, owner):
        with self.lock:
            db = self._open(owner)
            try:
                return [json.loads(row[0]) for row in db.execute(
                    'SELECT metadata_json FROM threads WHERE deleted=0 AND has_history=1 ORDER BY updated_at DESC,id')]
            finally:
                db.commit()
                db.close()

    def get(self, owner, key, deleted=False):
        self.valid_key(key)
        with self.lock:
            db = self._open(owner)
            try:
                row = db.execute('SELECT state_json FROM threads WHERE id=?', (key,)).fetchone()
                state = json.loads(row[0]) if row else None
                if state is None or (state.get('deleted') and not deleted):
                    raise SessionError('会话不存在。', 404)
                return state
            finally:
                db.commit()
                db.close()

    def purge_deleted(self, owner, key):
        """删除正文日志，仅保留可重建且能阻止旧导入复活的墓碑。"""
        self.valid_key(key)
        with self.lock:
            db = self._open(owner)
            temporary = None
            try:
                row = db.execute('SELECT state_json FROM threads WHERE id=?', (key,)).fetchone()
                state = json.loads(row[0]) if row else None
                if not state or not state.get('deleted'):
                    raise SessionError('会话尚未删除。')
                patch = {'fields': {k: v for k, v in state.items() if k not in ('nodes', 'runs', 'approvals', 'steering')},
                         'maps': {k: {'set': {}, 'delete': []} for k in ('nodes', 'runs', 'approvals', 'steering')}}
                record = {'schema_version': 1, 'session_id': key, 'ordinal': 1, 'timestamp': now(),
                          'type': 'session_tombstone', 'patch': patch}
                file = self.paths(owner)[1] / (key + '.jsonl')
                temporary = file.with_suffix('.' + uuid4().hex + '.tmp')
                data = (encode(record) + '\n').encode()
                with temporary.open('xb') as target:
                    os.chmod(temporary, 0o600)
                    target.write(data)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, file)
                self._project(db, key, state, 1, len(data))
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
                db.close()

    def mutate(self, owner, key, kind, operation, event=None):
        """在同一写锁内校验版本、追加持久事件并更新索引。"""
        self.valid_key(key)
        with self.lock:
            db = self._open(owner)
            try:
                row = db.execute('SELECT state_json FROM threads WHERE id=?', (key,)).fetchone()
                before = json.loads(row[0]) if row else {}
                state = copy.deepcopy(before)
                result = operation(state)
                patch = {'fields': {}, 'maps': {}}
                for name, value in state.items():
                    if name in ('nodes', 'runs', 'approvals', 'steering'):
                        previous = before.get(name, {})
                        change = {'set': {k: v for k, v in value.items() if k not in previous or previous[k] != v},
                                  'delete': [k for k in previous if k not in value]}
                        if name not in before or change['set'] or change['delete']:
                            patch['maps'][name] = change
                    elif name not in before or before[name] != value:
                        patch['fields'][name] = value
                if patch['fields'] or patch['maps'] or event is not None:
                    row = db.execute('SELECT ordinal,byte_offset FROM thread_history_projection_state WHERE thread_id=?', (key,)).fetchone()
                    ordinal = (row[0] if row else 0) + 1
                    record = {'schema_version': 1, 'session_id': key, 'ordinal': ordinal,
                              'timestamp': now(), 'type': kind, 'patch': patch}
                    if event is not None:
                        record['payload'] = event
                    file = self.paths(owner)[1] / (key + '.jsonl')
                    with file.open('ab') as target:
                        os.chmod(file, 0o600)
                        target.write((encode(record) + '\n').encode())
                        target.flush()
                        os.fsync(target.fileno())
                        offset = target.tell()
                    self._project(db, key, state, ordinal, offset)
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()


storage = SessionStorage()
