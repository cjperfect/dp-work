"""Argon2 密码哈希、旧 PBKDF2 兼容与 JWT 签发校验。"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from . import config

_passwords = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def _verify_legacy_password(password: str, stored: str) -> bool:
    """仅兼容历史 PBKDF2 格式，新密码由 pwdlib 管理。"""
    try:
        algo, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        if not 1 <= iterations <= 2_000_000:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        return _verify_legacy_password(password, stored)
    try:
        return _passwords.verify(password, stored)
    except (UnknownHashError, ValueError, TypeError):
        return False


def verify_password_and_update(password: str, stored: str) -> tuple[bool, str | None]:
    if stored.startswith("pbkdf2_sha256$"):
        valid = _verify_legacy_password(password, stored)
        return valid, hash_password(password) if valid else None
    try:
        return _passwords.verify_and_update(password, stored)
    except (UnknownHashError, ValueError, TypeError):
        return False, None


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
