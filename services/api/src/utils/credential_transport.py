"""JWE 密码传输：RSA-OAEP-256 包装一次性 AES-256-GCM 密钥。"""

import json
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from jwcrypto import jwe, jwk

from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode

ALGORITHM = "RSA-OAEP-256"
ENCRYPTION = "A256GCM"
MAX_AGE_SECONDS = 120
Purpose = Literal["login", "register"]


@lru_cache(maxsize=1)
def get_transport_key() -> jwk.JWK:
    """读取或创建密码传输私钥。"""
    path = Path(config.CREDENTIAL_PRIVATE_KEY_FILE)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = jwk.JWK.generate(kty="RSA", size=3072)
        # 临时文件默认 0600；原子发布，多个 worker 不覆盖彼此的私钥。
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                temporary.write(key.export_to_pem(private_key=True, password=None))
                temporary.flush()
                os.fsync(temporary.fileno())
                try:
                    os.link(temporary_path, path)
                except FileExistsError:
                    pass
            finally:
                temporary_path.unlink(missing_ok=True)
    key = jwk.JWK.from_pem(path.read_bytes())
    if (
        key.get("kty") != "RSA"
        or not key.has_private
        or key.get_op_key("decrypt").key_size < 2048
    ):
        raise RuntimeError("密码传输私钥必须为至少 2048 位的 RSA 私钥")
    return key


def public_encryption_key() -> dict:
    """获取密码传输公钥。"""
    key = get_transport_key()
    return {
        "key_id": key.thumbprint(),
        "algorithm": ALGORITHM,
        "encryption": ENCRYPTION,
        "public_key": key.export_public(as_dict=True),
        "server_time": int(time.time()),
    }


def decrypt_password(ciphertext: str, username: str, purpose: Purpose) -> str:
    """解密并校验密码凭证。"""
    key = get_transport_key()
    try:
        if len(ciphertext.split(".")) != 5:
            raise ValueError("compact JWE required")
        envelope = jwe.JWE(algs=[ALGORITHM, ENCRYPTION])
        envelope.deserialize(ciphertext)
        if envelope.jose_header != {
            "alg": ALGORITHM,
            "enc": ENCRYPTION,
            "kid": key.thumbprint(),
        }:
            raise ValueError("unexpected encryption headers")
        envelope.decrypt(key)
        payload = json.loads(envelope.payload)
        now = time.time()
        issued_at = payload.get("issued_at")
        password = payload.get("password")
        if (
            payload.get("username") != username
            or payload.get("purpose") != purpose
            or type(issued_at) is not int
            or issued_at > now + 5
            or now - issued_at > MAX_AGE_SECONDS
            or not isinstance(password, str)
            or not password
        ):
            raise ValueError("invalid credential payload")
        return password
    except (ValueError, TypeError, AttributeError, jwe.InvalidJWEData):
        raise ApiError(
            ApiCode.PARAM_ERROR, "登录凭证无效或已过期，请重新提交。", 400
        ) from None
