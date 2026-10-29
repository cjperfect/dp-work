"""会话图片保存在当前账号的本机目录，消息只保存附件引用。"""
import base64
import hashlib
import re
import os
from uuid import uuid4
from .storage import storage, SessionError

MAX_BYTES = 1024 * 1024
TYPES = {'image/png': b'\x89PNG\r\n\x1a\n', 'image/jpeg': b'\xff\xd8\xff', 'image/webp': b'RIFF'}


def image_path(owner, image_id):
    if not re.fullmatch(r'[a-f0-9]{64}', image_id):
        raise SessionError('图片标识无效。', 400)
    database, _ = storage.paths(owner)
    root = database.parent / 'attachments'
    if root.is_symlink(): raise SessionError('附件目录无效。', 400)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / image_id
    if path.is_symlink(): raise SessionError('图片路径无效。', 400)
    return path


def save(owner, body):
    value, mime = body.get('data_url', ''), body.get('content_type')
    if mime not in TYPES or not isinstance(value, str) or not value.startswith(f'data:{mime};base64,') or len(value) > MAX_BYTES * 2:
        raise SessionError('仅支持 PNG、JPEG、WebP 图片，每张不超过 1 MB。', 400)
    try: data = base64.b64decode(value.split(',', 1)[1], validate=True)
    except ValueError as cause: raise SessionError('图片数据无效。', 400) from cause
    if not data or len(data) > MAX_BYTES or not data.startswith(TYPES[mime]) or (mime == 'image/webp' and data[8:12] != b'WEBP'):
        raise SessionError('图片格式无效或超过 1 MB。', 400)
    image_id = hashlib.sha256(data).hexdigest()
    path = image_path(owner, image_id)
    if not path.exists():
        temporary = path.with_name('.' + str(uuid4()) + '.tmp')
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'id': image_id, 'name': str(body.get('name') or '图片')[:200], 'content_type': mime}


def read(owner, image_id, mime):
    if mime not in TYPES: raise SessionError('图片类型无效。', 400)
    try: data = image_path(owner, image_id).read_bytes()
    except FileNotFoundError as cause: raise SessionError('本机图片已丢失，请重新粘贴。', 404) from cause
    if len(data) > MAX_BYTES or not data.startswith(TYPES[mime]): raise SessionError('图片数据无效。', 400)
    return f'data:{mime};base64,' + base64.b64encode(data).decode()


def model_images(owner, refs):
    if not isinstance(refs, list) or len(refs) > 3: raise SessionError('每条消息最多 3 张图片。', 400)
    if any(not isinstance(ref, dict) or not isinstance(ref.get('id'), str) or ref.get('content_type') not in TYPES for ref in refs):
        raise SessionError('图片引用无效。', 400)
    return [read(owner, ref['id'], ref['content_type']) for ref in refs]
