"""用户名密码注册的 HTTP 流程测试，不连接外部数据库。"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from app.core.security import hash_password
from app.main import app
from app.modules.auth import dependencies as deps
from app.modules.auth import service as auth
from app.modules.users import service as user_model
from app.modules.users.exceptions import UsernameExistsError
from app.modules.users.models import User
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def accounts(monkeypatch):
    users = {}

    async def create_user(
        *, username, password, display_name, department, role, allow_existing
    ):
        assert allow_existing is False
        if username in users:
            raise UsernameExistsError(username)
        user = User(
            id=f"u-{username}",
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
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
            created = await client.post("/api/v1/auth/register", json=payload)
            assert created.status_code == 201
            data = created.json()["data"]
            assert data["user"]["role"] == "member"
            assert data["user"]["department"] == "unassigned"
            assert data["user"]["display_name"] == "test_member"
            assert "password_hash" not in data["user"]
            assert accounts["test_member"].password_hash != payload["password"]
            login = await client.post("/api/v1/auth/login", json=payload)
            assert login.status_code == 200
            me = await client.get(
                "/api/v1/auth/users/me",
                headers={"Authorization": f"Bearer {data['token']}"},
            )
            assert me.status_code == 200
            assert me.json()["data"]["username"] == "test_member"
            wrong = await client.post(
                "/api/v1/auth/login", json={**payload, "password": "wrong"}
            )
            assert wrong.status_code == 401

    asyncio.run(case())


def test_duplicate_registration_never_returns_existing_identity(accounts):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            original = {"username": "same_name", "password": "original-password"}
            await client.post("/api/v1/auth/register", json=original)
            duplicate = await client.post(
                "/api/v1/auth/register",
                json={**original, "password": "different-password"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["data"] is None
            assert (
                await client.post("/api/v1/auth/login", json=original)
            ).status_code == 200

    asyncio.run(case())


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "a", "password": "password123"},
        {"username": "bad name", "password": "password123"},
        {"username": "tester", "password": "short"},
        {"username": "tester", "password": "password123", "role": "admin"},
        {"username": "tester", "password": "password123", "department": "finance"},
    ],
)
def test_invalid_registration_rejected(accounts, payload):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/auth/register", json=payload)
            assert response.status_code == 422
            assert accounts == {}

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
                "Existing",
                "unassigned",
                allow_existing=False,
            )
        lookup.assert_not_awaited()

    asyncio.run(case())
