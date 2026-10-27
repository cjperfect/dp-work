"""认证安全：密码哈希（pbkdf2，标准库零编译依赖）+ JWT 签发/校验。"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

import jwt

from . import config

# 密码哈希格式：pbkdf2_sha256$iterations$salt_hex$hash_hex
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """生成密码哈希。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """验证密码。"""
    try:
        algo, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations_s)
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(sub: int, role: str, dept: str) -> str:
    """签发访问令牌。"""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(sub),
        "uidv": 2,
        "role": role,
        "dept": dept,
        "iat": now,
        "exp": now + config.JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def decode_token(token: str) -> dict[str, Any] | None:
    """解析并验证访问令牌。"""
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
