"""旧账号逐步升级哈希，错误密码或停用账号不会写入。"""

import asyncio
import hashlib
from unittest.mock import AsyncMock
import pytest
from src.core.security import hash_password, verify_password, verify_password_and_update
from src.core.exceptions import ApiError
from src.modules.auth import service
from src.modules.users.models import User


def legacy(password):
    salt = bytes.fromhex("10203040506070801020304050607080")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000).hex()
    return f"pbkdf2_sha256$200000${salt.hex()}${digest}"


def test_argon2_and_legacy_hashes():
    stored = hash_password("test-password")
    assert stored.startswith("$argon2id$")
    assert verify_password("test-password", stored)
    assert not verify_password("wrong", stored)
    assert verify_password_and_update("test-password", stored) == (True, None)
    valid, updated = verify_password_and_update(
        "test-password", legacy("test-password")
    )
    assert (
        valid
        and updated.startswith("$argon2id$")
        and verify_password("test-password", updated)
    )
    for bad in ("garbage", "pbkdf2_sha256$-1$aa$bb", "pbkdf2_sha256$999999999$aa$bb"):
        assert verify_password_and_update("wrong", bad) == (False, None)


@pytest.mark.parametrize(
    "active, password",
    [(True, "test-password"), (True, "wrong"), (False, "test-password")],
)
def test_login_upgrade_only_for_authenticated_active_user(
    monkeypatch, active, password
):
    old = legacy("test-password")
    user = User(
        id=7,
        username="fixture",
        role="member",
        department="product",
        status=0 if active else 1,
        password_hash=old,
    )
    upgrade = AsyncMock()
    monkeypatch.setattr(
        service.users_service, "find_by_username", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service.users_service, "upgrade_password_hash", upgrade)

    async def run():
        if active and password == "test-password":
            result = await service.login("fixture", password)
            assert result["user"]["id"] == 7
            args = upgrade.await_args.args
            assert args[:2] == (7, old) and verify_password(password, args[2])
        else:
            with pytest.raises(ApiError):
                await service.login("fixture", password)
            upgrade.assert_not_awaited()

    asyncio.run(run())
