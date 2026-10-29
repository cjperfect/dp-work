"""本机按账号隔离服务设置；密钥加密保存且不通过读取接口返回。"""
import json
import os
import tempfile
import threading
from pathlib import Path

from cryptography.fernet import Fernet
from .. import config
from .settings import RuntimeConfig, defaults
from .settings_schema import ServiceConfig

LOCK = threading.RLock()


def paths(owner):
    if type(owner) is not int or owner <= 0:
        raise ValueError('用户身份无效。')
    root = config.DATA_ROOT / 'config' / 'users' / str(owner)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root / 'services.json', root / 'services.key'


def atomic(file, content):
    """同目录临时写入后原子替换，失败时保留原配置。"""
    with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
            target.close()
            os.replace(temporary, file)
        finally:
            temporary.unlink(missing_ok=True)


def cipher(owner):
    _, file = paths(owner)
    if not file.exists():
        with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as target:
            temporary = Path(target.name)
            try:
                target.write(Fernet.generate_key())
                target.flush()
                os.fsync(target.fileno())
                try:
                    os.link(temporary, file)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
    return Fernet(file.read_bytes())


def load(owner):
    file, _ = paths(owner)
    if not file.exists():
        return {}
    data = json.loads(file.read_text())
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('本机服务配置损坏，请从备份恢复。')
    return data


def kind_config(kind, body):
    if kind not in ('model', 'asr') or (kind == 'asr') != (body.provider == 'doubao'):
        raise ValueError('服务商与配置类型不匹配。')


def runtime(owner, kind):
    """执行器直接解密读取，返回值仅在 Sidecar 内存中使用。"""
    if owner is None:
        return None
    with LOCK:
        row = load(owner).get(kind, {})
        data = row.get('config', {})
        if not data.get('enabled'):
            return None
        if not row.get('key'):
            raise ValueError('个人服务尚未配置 API Key。')
        key = cipher(owner).decrypt(row['key'].encode()).decode()
        return RuntimeConfig(**data, api_key=key)


def read(owner):
    with LOCK:
        data, platform = load(owner), defaults()
        result = {}
        for kind in ('model', 'asr'):
            row = data.get(kind, {})
            result[kind] = {**platform[kind], **row.get('config', {}),
                            'has_api_key': bool(row.get('key')), 'enabled': bool(row.get('config', {}).get('enabled')),
                            'default': platform[kind]}
        return result


def prepare(owner, kind, body):
    """保留未提交的密钥；服务商变化时不得复用旧服务商密钥。"""
    body = ServiceConfig.model_validate(body)
    kind_config(kind, body)
    data = load(owner)
    previous = data.get(kind, {})
    encrypted = previous.get('key')
    if body.clear_api_key or previous.get('config', {}).get('provider', body.provider) != body.provider:
        encrypted = None
    if body.api_key is not None:
        encrypted = cipher(owner).encrypt(body.api_key.get_secret_value().strip().encode()).decode()
    if body.enabled and not encrypted:
        raise ValueError('启用个人配置前请填写 API Key。')
    row = {'config': body.model_dump(exclude={'api_key', 'clear_api_key'}), 'key': encrypted}
    return data, row


def save(owner, kind, body):
    with LOCK:
        data, row = prepare(owner, kind, body)
        data.update(schema_version=1)
        data[kind] = row
        atomic(paths(owner)[0], json.dumps(data, ensure_ascii=False, indent=2).encode())
    return {'saved': True}


def test_config(owner, kind, body):
    """测试表单使用已有密钥，但不修改已保存设置。"""
    with LOCK:
        _, row = prepare(owner, kind, body)
        if not row['config']['enabled']:
            return None
        return RuntimeConfig(**row['config'], api_key=cipher(owner).decrypt(row['key'].encode()).decode())
