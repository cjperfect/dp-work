"""本机文件快照、Bash 前后比较及带冲突检查的单文件撤销。"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
from uuid import uuid4

from .. import config
from .file_changes import build_change

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 3000
MAX_ENTRIES = 20000
EXCLUDED = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.dp-work', '.next', 'dist', 'build'}
LOCKS = {}
LOCKS_GUARD = threading.Lock()


class SnapshotError(Exception):
    pass


def workspace_lock(root):
    """同一目录的工具写入、命令和撤销串行执行。"""
    with LOCKS_GUARD:
        return LOCKS.setdefault(str(Path(root).resolve()), threading.Lock())


def store_root(owner):
    """快照按本机账号隔离，不发送前端或云端。"""
    root = config.WORKSPACE_DIR.parent / 'data' / 'file-snapshots' / str(int(owner or 0))
    for path in (root, root / 'blobs', root / 'batches', root / 'changes', root / 'runs'):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise SnapshotError('快照目录不能使用软链接。')
    return root


def write_atomic(path, data):
    """原子落盘；只将完整快照发布给后续操作。"""
    temporary = path.with_name('.' + uuid4().hex)
    try:
        with temporary.open('xb') as output:
            os.chmod(temporary, 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_json(path, value):
    write_atomic(path, json.dumps(value, ensure_ascii=False).encode('utf-8'))


@contextmanager
def parent_handle(root, relative, create=False):
    """逐级拒绝软链接；POSIX 使用目录句柄约束恢复路径。"""
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(part in ('..', '.') or '\\' in part or ':' in part or any(ord(char) < 32 for char in part) for part in parts):
        raise SnapshotError('文件路径无效。')
    fds = []
    try:
        if os.name != 'nt':
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open(root, flags)
            fds.append(fd)
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o755, dir_fd=fd)
                    except FileExistsError:
                        pass
                fd = os.open(part, flags, dir_fd=fd)
                fds.append(fd)
            yield fd, parts[-1]
        else:
            path = Path(root)
            for part in parts[:-1]:
                path /= part
                if create:
                    path.mkdir(exist_ok=True)
                if path.is_symlink() or path.is_junction():
                    raise SnapshotError('不能通过软链接或目录联接恢复文件。')
            yield None, str(path / parts[-1])
    finally:
        for fd in reversed(fds):
            os.close(fd)


def read_state(root, relative, blobs=None):
    """区分不存在、普通文件及不可恢复对象，限制单文件备份大小。"""
    try:
        with parent_handle(root, relative) as (directory, name):
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                return {'kind': 'unsupported', 'stamp': [info.st_mode, info.st_mtime_ns, info.st_ino]}
            base = {'kind': 'file', 'mode': stat.S_IMODE(info.st_mode), 'size': info.st_size}
            if info.st_size > MAX_FILE_BYTES:
                return {**base, 'unavailable': '文件超过 2 MB，未保存可撤销快照。', 'stamp': [info.st_mtime_ns, info.st_ino]}
            fd = os.open(name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0), dir_fd=directory)
            with os.fdopen(fd, 'rb') as source:
                actual = os.fstat(source.fileno())
                if not stat.S_ISREG(actual.st_mode):
                    raise SnapshotError('文件类型发生变化，请重试。')
                data = source.read(MAX_FILE_BYTES + 1)
                end = os.fstat(source.fileno())
            if len(data) > MAX_FILE_BYTES or (actual.st_ino, actual.st_size, actual.st_mtime_ns) != (end.st_ino, end.st_size, end.st_mtime_ns):
                raise SnapshotError('文件正在被其他程序修改，请重试。')
            digest = hashlib.sha256(data).hexdigest()
            if blobs is not None and not (blobs / digest).exists():
                write_atomic(blobs / digest, data)
            return {**base, 'size': len(data), 'mode': stat.S_IMODE(actual.st_mode), 'hash': digest}
    except FileNotFoundError:
        return {'kind': 'missing'}
    except OSError as cause:
        raise SnapshotError('无法读取文件快照，请检查目录权限或软链接。') from cause


def scan(root):
    """有界扫描源码目录，不遍历依赖、Git 元数据或软链接目录。"""
    paths, stack, count = [], [Path(root)], 0
    while stack:
        folder = stack.pop()
        if folder.is_symlink() or (os.name == 'nt' and folder.is_junction()):
            continue
        with os.scandir(folder) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise SnapshotError('目录扫描超过 20000 项，请缩小工作目录后执行。')
                if entry.name in EXCLUDED:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                else:
                    paths.append(Path(entry.path).relative_to(root).as_posix())
                if len(paths) > MAX_FILES:
                    raise SnapshotError('待跟踪文件超过 3000 个，请缩小工作目录后执行。')
    return paths


class SnapshotBatch:
    """先保存基线，再允许修改；相同内容的备份在账号内复用。"""
    def __init__(self, root, owner=0, paths=None, run_id=None):
        self.root = Path(root).resolve(strict=True)
        self.store = store_root(owner)
        self.id = str(uuid4())
        self.tree = paths is None
        self.run_id = run_id
        info = self.root.stat()
        self.identity = [info.st_dev, info.st_ino]
        self.before = {}
        total = 0
        for relative in scan(self.root) if self.tree else paths:
            state = read_state(self.root, relative, self.store / 'blobs')
            total += state.get('size', 0) if 'hash' in state else 0
            if total > MAX_TOTAL_BYTES:
                raise SnapshotError('文件快照超过单次 32 MB 预算，请缩小工作目录后执行。')
            self.before[relative] = state
        save_json(self.store / 'batches' / (self.id + '.json'),
                  {'root': str(self.root), 'identity': self.identity, 'files': self.before})

    def text(self, state):
        if state['kind'] == 'missing':
            return ''
        if 'hash' not in state or state.get('size', 0) > 256000:
            return None
        try:
            data = (self.store / 'blobs' / state['hash']).read_bytes()
            return data.decode('utf-8') if b'\x00' not in data else None
        except (OSError, UnicodeError):
            return None

    def finish(self):
        """记录成功、失败、超时后实际留下的变化，不假定工具返回等于磁盘结果。"""
        info = self.root.lstat()
        if [info.st_dev, info.st_ino] != self.identity or self.root.is_symlink():
            raise SnapshotError('执行期间工作目录被替换，未继续扫描。')
        current = set(scan(self.root)) if self.tree else set(self.before)
        changes = []
        preview_bytes = 0
        for relative in sorted(current | self.before.keys()):
            before = self.before.get(relative, {'kind': 'missing'})
            after = read_state(self.root, relative)
            if before == after:
                continue
            if after.get('size', MAX_FILE_BYTES) <= 256000 and preview_bytes + after.get('size', 0) <= MAX_TOTAL_BYTES:
                after = read_state(self.root, relative, self.store / 'blobs')
                preview_bytes += after.get('size', 0)
            change = build_change(self.root / relative, self.text(before), self.text(after)) or {
                'id': str(uuid4()), 'path': str(self.root / relative), 'lines': [], 'additions': 0, 'deletions': 0}
            reason = next((state.get('unavailable') or ('软链接或特殊文件不支持撤销。' if state['kind'] == 'unsupported' else None)
                           for state in (before, after) if state.get('unavailable') or state['kind'] == 'unsupported'), None)
            change.update(kind='created' if before['kind'] == 'missing' else 'deleted' if after['kind'] == 'missing' else 'modified',
                          undoable=reason is None, **({'undo_unavailable': reason} if reason else {}))
            save_json(self.store / 'changes' / (change['id'] + '.json'),
                      {'root': str(self.root), 'identity': self.identity, 'relative': relative,
                       'before': before, 'after': after, 'change': change, 'batch_id': self.id})
            changes.append(change)
            if self.run_id and re.fullmatch(r'[a-f0-9-]{36}', self.run_id):
                index = self.store / 'runs' / (self.run_id + '.json')
                ids = json.loads(index.read_text()) if index.exists() else []
                save_json(index, [*ids, change['id']])
        return changes


def run_changes(owner, run_id):
    """从磁盘补齐被取消的流没来得及送达的实际文件修改。"""
    if not re.fullmatch(r'[a-f0-9-]{36}', run_id):
        return []
    store = config.WORKSPACE_DIR.parent / 'data' / 'file-snapshots' / str(int(owner or 0))
    index = store / 'runs' / (run_id + '.json')
    if not index.exists():
        return []
    changes = []
    for change_id in json.loads(index.read_text()):
        record = json.loads((store / 'changes' / (change_id + '.json')).read_text())
        changes.append({**record['change'], **({'undone': True} if record.get('undone') else {})})
    return changes


def restore_file(root, relative, before, data):
    """原子替换普通文件；不会沿父目录软链接写到工作目录以外。"""
    with parent_handle(root, relative, create=before['kind'] != 'missing') as (directory, name):
        if before['kind'] == 'missing':
            os.unlink(name, dir_fd=directory)
            return
        temporary = '.dp-work-restore-' + uuid4().hex
        if directory is None:
            temporary = str(Path(name).with_name(temporary))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                if os.name != 'nt':
                    os.fchmod(output.fileno(), before['mode'])
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass


def undo(owner, change_id, expected_root):
    """只恢复账号自己的已记录修改；后续内容不同则拒绝覆盖。"""
    if not isinstance(change_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', change_id):
        raise SnapshotError('文件修改 ID 无效。')
    store = store_root(owner)
    path = store / 'changes' / (change_id + '.json')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as cause:
        raise SnapshotError('修改前快照不存在，旧记录不支持撤销。') from cause
    root = Path(record['root'])
    if root != Path(expected_root).resolve() or root.resolve() != root or [root.stat().st_dev, root.stat().st_ino] != record['identity']:
        raise SnapshotError('原工作目录已变化或授权已失效，不能撤销。')
    if not record['change'].get('undoable'):
        raise SnapshotError(record['change'].get('undo_unavailable', '此修改不支持撤销。'))
    lock = workspace_lock(root)
    if not lock.acquire(blocking=False):
        raise SnapshotError('工作目录正在执行文件操作，请结束后再撤销。')
    try:
        current = read_state(root, record['relative'])
        if record.get('undone'):
            return {**record['change'], 'undone': True}
        if current != record['before']:
            if current != record['after']:
                raise SnapshotError('文件已有后续修改，请先撤销最近的修改；不会覆盖当前内容。')
            data = b''
            if record['before'].get('hash'):
                digest = record['before']['hash']
                if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
                    raise SnapshotError('快照引用无效，未修改文件。')
                data = (store / 'blobs' / digest).read_bytes()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise SnapshotError('快照校验失败，未修改文件。')
            restore_file(root, record['relative'], record['before'], data)
        record['undone'] = True
        save_json(path, record)
        return {**record['change'], 'undone': True}
    finally:
        lock.release()
