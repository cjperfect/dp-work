import asyncio
import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.utils import credential_transport as transport
from app.core.exceptions import ApiError
from app.main import app
from tests.credentials import auth_payload

# 保留未被 autouse fixture 替换的磁盘加载函数，专门测试临时目录。
load_key_from_disk = transport.get_transport_key


def test_encryption_key_contains_only_public_material():
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/auth/encryption-key")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            data = response.json()["data"]
            assert data["public_key"]["kty"] == "RSA"
            assert {"n", "e"}.issubset(data["public_key"])
            assert not {"d", "p", "q", "dp", "dq", "qi"}.intersection(
                data["public_key"]
            )
            assert data["algorithm"] == "RSA-OAEP-256"
            assert data["encryption"] == "A256GCM"

    asyncio.run(case())


@pytest.mark.parametrize("purpose", ["login", "register"])
def test_plaintext_passwords_are_rejected_and_never_echoed(purpose):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            password = "secret-do-not-echo"
            response = await client.post(
                f"/api/auth/{purpose}",
                json={"username": "tester", "password": password},
            )
            assert response.status_code == 422
            assert password not in response.text
            assert all("input" not in error for error in response.json()["data"])

    asyncio.run(case())


def test_long_unicode_password_round_trip():
    password = "密😀" * 300
    payload = auth_payload("测试 用户", password, "register")
    assert (
        transport.decrypt_password(
            payload["encrypted_password"], "测试 用户", "register"
        )
        == password
    )
    assert password not in json.dumps(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "register"},
        {"username": "different-user"},
        {"issued_at": 1},
        {"issued_at": int(time.time()) + 3600},
        {"password": ""},
    ],
)
def test_invalid_encrypted_credentials_are_rejected(change):
    payload = auth_payload("tester", "secret", **change)
    with pytest.raises(ApiError) as error:
        transport.decrypt_password(payload["encrypted_password"], "tester", "login")
    assert error.value.status_code == 400
    assert "secret" not in str(error.value)


def test_tampered_ciphertext_is_rejected():
    payload = auth_payload("tester", "secret")
    parts = payload["encrypted_password"].split(".")
    parts[3] = ("A" if parts[3][0] != "A" else "B") + parts[3][1:]
    with pytest.raises(ApiError):
        transport.decrypt_password(".".join(parts), "tester", "login")


def test_private_key_is_persistent_and_restricted_to_owner(tmp_path, monkeypatch):
    path = tmp_path / "keys/auth.pem"
    monkeypatch.setattr(transport.config, "CREDENTIAL_PRIVATE_KEY_FILE", str(path))
    load_key_from_disk.cache_clear()
    try:
        first = load_key_from_disk().thumbprint()
        assert path.stat().st_mode & 0o777 == 0o600
        load_key_from_disk.cache_clear()
        assert load_key_from_disk().thumbprint() == first
        assert list(path.parent.iterdir()) == [path]
    finally:
        load_key_from_disk.cache_clear()
