"""项目元数据保存在当前账号 SQLite，目录授权仍来自 Electron 原生选择器。"""
import json
import os
import sqlite3
from uuid import UUID

from .storage import storage, SessionError, now
from .. import config
from ..tools.projects import project_workspace


def registry(owner, key, device=None, path=None):
    """客户端提交的路径不能代替本机原生目录授权。"""
    try:
        UUID(key)
        file = config.WORKSPACE_DIR.parent / 'data/projects.json'
        if file.is_symlink() or file.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('invalid registry')
        item = json.loads(file.read_text())['projects'][key]
        if item['owner_id'] != owner or (device and item['device_id'] != device):
            raise ValueError('wrong owner or device')
        resolved = project_workspace(key, owner)
        if path is not None and os.path.normcase(str(resolved)) != os.path.normcase(path):
            raise ValueError('wrong path')
        return item
    except (OSError, ValueError, KeyError, TypeError) as cause:
        raise SessionError('项目目录未在当前设备授权，请重新选择文件夹。', 409) from cause


def get(owner, key, device=None):
    """只读取已登记且未删除的本机项目，不自动把目录授权加入列表。"""
    UUID(key)
    file, _ = storage.paths(owner)
    db = sqlite3.connect(file, timeout=10)
    try:
        row = db.execute('SELECT data_json FROM projects WHERE id=? AND deleted=0', (key,)).fetchone()
        if not row:
            raise SessionError('项目不存在。', 404)
        data = json.loads(row[0])
        if device and data['device_id'] != device:
            raise SessionError('项目属于另一台设备，请重新选择本地文件夹。')
        registry(owner, key, data['device_id'], data['path'])
        return data
    finally:
        db.close()


def operation(action, owner, body, device):
    """原子保存项目元数据；删除只解除会话关联，保留用户文件。"""
    from .service import unlocked, touch
    with storage.lock:
        db = storage._open(owner)
        try:
            if action == 'list':
                return [json.loads(row[0]) for row in db.execute('SELECT data_json FROM projects WHERE deleted=0 ORDER BY updated_at DESC,id')]
            key = body['id']
            UUID(key)
            existing = db.execute('SELECT data_json,deleted FROM projects WHERE id=?', (key,)).fetchone()
            if action == 'create':
                registry(owner, key, device, body['path'])
                if body['device_id'] != device:
                    raise SessionError('项目设备不匹配。')
                if existing and not existing[1]:
                    previous = json.loads(existing[0])
                    if previous['device_id'] != device or previous['path'] != body['path']:
                        raise SessionError('项目目录不匹配。')
                    return previous
                if not body['name'].strip():
                    raise SessionError('请输入项目名称。', 400)
                timestamp = now()
                data = {k: body[k] for k in ('id','name','path','device_id')}
                data.update(name=body['name'].strip(), created_at=timestamp, updated_at=timestamp)
            else:
                if not existing or existing[1]:
                    raise SessionError('项目不存在。', 404)
                data = json.loads(existing[0])
                if data['device_id'] != device:
                    raise SessionError('项目属于另一台设备。')
                if action == 'get':
                    registry(owner, key, device, data['path'])
                    return data
                if action == 'rename':
                    if not body['name'].strip():
                        raise SessionError('请输入项目名称。',400)
                    data.update(name=body['name'].strip(),updated_at=now())
                elif action == 'delete':
                    states = [json.loads(row[0]) for row in db.execute('SELECT state_json FROM threads WHERE deleted=0')]
                    targets = [s for s in states if s['thread']['project_id'] == key]
                    for state in targets:
                        unlocked(state)
                    # 释放事务，持有进程写锁依次提交会话日志；中断后重试安全。
                    db.commit()
                    for state in targets:
                        def clear(s):
                            unlocked(s)
                            s['thread']['project_id'] = None
                            touch(s)
                        storage.mutate(owner,state['thread']['id'],'project_detached',clear)
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('UPDATE projects SET deleted=1,updated_at=? WHERE id=?',(now(),key))
                    return None
                else:
                    raise SessionError('不支持的项目操作。',400)
            db.execute('INSERT OR REPLACE INTO projects VALUES (?,?,0,?)',(key,data['updated_at'],json.dumps(data,ensure_ascii=False)))
            return data
        except BaseException:
            db.rollback()
            raise
        finally:
            if db.in_transaction:
                db.commit()
            db.close()
