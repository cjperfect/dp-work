"""用户名密码注册的 HTTP 流程测试，不连接外部数据库。"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password
from app.main import app
from app.modules.auth import dependencies as deps
from app.modules.auth import service as auth
from app.modules.users import service as user_model
from app.modules.users.exceptions import UsernameExistsError
from app.modules.users.models import User
from tests.credentials import protect


@pytest.fixture
def accounts(monkeypatch):
    users = {}

    async def create_user(*, username, password, department, role, allow_existing):
        assert allow_existing is False
        if username in users:
            raise UsernameExistsError(username)
        user = User(
            id=len(users) + 1,
            username=username,
            password_hash=hash_password(password),
            department=department,
            role=role,
            status=0,
        )
        users[username] = user
        return user

    async def find_by_username(username):
        return users.get(username)

    async def find_by_id(user_id):
        return next((user for user in users.values() if user.id == user_id), None)

    monkeypatch.setattr(auth.users_service, "create_user", create_user)
    monkeypatch.setattr(auth.users_service, "find_by_username", find_by_username)
    monkeypatch.setattr(deps.users_service, "find_by_id", find_by_id)
    return users


def test_register_login_and_restore(accounts):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"username": "test_member", "password": "test-password-123"}
            created = await client.post(
                "/api/auth/register", json=protect(payload, "register")
            )
            assert created.status_code == 200
            data = created.json()["data"]
            assert isinstance(data["user"]["id"], int)
            assert data["user"]["role"] == "member"
            assert data["user"]["department"] == "unassigned"
            assert "display_name" not in data["user"]
            assert "password_hash" not in data["user"]
            assert accounts["test_member"].password_hash != payload["password"]
            login = await client.post(
                "/api/auth/login", json=protect(payload, "login")
            )
            assert login.status_code == 200
            assert login.json()["data"]["user"]["username"] == "test_member"
            assert "password_hash" not in login.json()["data"]["user"]
            wrong = await client.post(
                "/api/auth/login",
                json=protect({**payload, "password": "wrong"}, "login"),
            )
            assert wrong.status_code == 401

    asyncio.run(case())


def test_duplicate_registration_never_returns_existing_identity(accounts):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            original = {"username": "same_name", "password": "original-password"}
            await client.post(
                "/api/auth/register", json=protect(original, "register")
            )
            duplicate = await client.post(
                "/api/auth/register",
                json=protect(
                    {**original, "password": "different-password"}, "register"
                ),
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["data"] is None
            assert (
                await client.post("/api/auth/login", json=protect(original, "login"))
            ).status_code == 200

    asyncio.run(case())


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "", "password": "password123"},
        {"username": "   ", "password": "password123"},
        {"username": "tester", "password": ""},
        {"username": "tester", "password": "password123", "role": "admin"},
    ],
)
def test_invalid_registration_rejected(accounts, payload):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/auth/register", json=protect(payload, "register")
            )
            assert response.status_code == (400 if not payload["password"] else 422)
            assert accounts == {}

    asyncio.run(case())


@pytest.mark.parametrize(
    ("username", "password"),
    [("a", "p"), ("bad name", "short"), ("u" * 64, "p" * 256)],
)
def test_registration_and_login_have_no_length_restrictions(
    accounts, username, password
):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"username": username, "password": password}
            assert (
                await client.post(
                    "/api/auth/register", json=protect(payload, "register")
                )
            ).status_code == 200
            assert (
                await client.post("/api/auth/login", json=protect(payload, "login"))
            ).status_code == 200

    asyncio.run(case())


def test_database_conflict_is_rejected_for_registration(monkeypatch):
    """ON CONFLICT 竞争失败后，注册不能走种子账号的幂等返回逻辑。"""

    @asynccontextmanager
    async def fake_transaction():
        yield AsyncMock()

    monkeypatch.setattr(user_model.session, "transaction", fake_transaction)
    monkeypatch.setattr(
        user_model.UserRepository, "insert", AsyncMock(return_value=None)
    )
    lookup = AsyncMock()
    monkeypatch.setattr(user_model.UserRepository, "find_by_username", lookup)

    async def case():
        with pytest.raises(UsernameExistsError):
            await user_model.create_user(
                "existing",
                "password123",
                "unassigned",
                allow_existing=False,
            )
        lookup.assert_not_awaited()

    asyncio.run(case())
