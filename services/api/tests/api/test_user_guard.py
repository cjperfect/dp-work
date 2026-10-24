"""真实 JWT + 模拟用户存储验证装饰器，包含 FastAPI 参数与依赖兼容性。"""

from __future__ import annotations

import asyncio
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import register_exception_handlers
from app.core.security import create_access_token
from app.decorators import require_user
from app.modules.auth import dependencies
from app.modules.users.models import User
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel


class GuardBody(BaseModel):
    title: str


@pytest.fixture
def guarded_app(monkeypatch):
    application = FastAPI()
    register_exception_handlers(application)
    user = User(
        id="guard-user",
        username="guard",
        password_hash="unused",
        display_name="Guard",
        department="finance",
        role="admin",
        status=0,
    )
    lookup = AsyncMock(return_value=user)
    monkeypatch.setattr(dependencies.users_service, "find_by_id", lookup)
    calls = []

    @application.post("/guard/{item_id}")
    @require_user(roles=("admin", "manager"), departments=("finance",))
    async def guarded(
        item_id: int,
        body: GuardBody,
        request: Request,
        user: Annotated[User, Depends(dependencies.get_current_user)],
        limit: int = 10,
    ) -> dict:
        calls.append(item_id)
        assert request.state.user is user
        return {"id": item_id, "title": body.title, "limit": limit, "user": user.id}

    @application.get("/guard-sync")
    @require_user()
    def guarded_sync() -> dict:
        return {"ok": True}

    return application, user, lookup, calls


def request(application, method="POST", url="/guard/42?limit=3", **kwargs):
    async def case():
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(case())


def headers(user):
    # 刻意使令牌中的权限过期：权限应以数据库查询到的用户为准。
    token = create_access_token(user.id, "member", "unassigned")
    return {"Authorization": f"Bearer {token}"}


def test_guard_preserves_body_path_query_user_injection_and_caches_lookup(guarded_app):
    application, user, lookup, calls = guarded_app
    response = request(application, headers=headers(user), json={"title": "Meeting"})
    assert response.status_code == 200
    assert response.json() == {
        "id": 42,
        "title": "Meeting",
        "limit": 3,
        "user": user.id,
    }
    lookup.assert_awaited_once_with(user.id)
    assert calls == [42]


@pytest.mark.parametrize("authorization", [None, "Basic invalid", "Bearer invalid"])
def test_guard_rejects_missing_or_invalid_credentials(guarded_app, authorization):
    application, _, lookup, calls = guarded_app
    response = request(
        application,
        headers={"Authorization": authorization} if authorization else {},
        json={"title": "Meeting"},
    )
    assert response.status_code == 401
    lookup.assert_not_awaited()
    assert calls == []


@pytest.mark.parametrize(
    ("role", "department", "status", "expected"),
    [
        ("member", "finance", 0, 403),
        ("admin", "engineering", 0, 403),
        ("admin", "finance", 1, 401),
        ("manager", "finance", 0, 200),
    ],
)
def test_guard_uses_current_account_status_and_permissions(
    guarded_app, role, department, status, expected
):
    application, user, _, calls = guarded_app
    user.role, user.department, user.status = role, department, status
    response = request(application, headers=headers(user), json={"title": "Meeting"})
    assert response.status_code == expected
    assert calls == ([42] if expected == 200 else [])


def test_deleted_user_rejected(guarded_app):
    application, user, lookup, calls = guarded_app
    lookup.return_value = None
    assert (
        request(
            application, headers=headers(user), json={"title": "Meeting"}
        ).status_code
        == 401
    )
    assert calls == []


def test_sync_endpoint_and_openapi(guarded_app):
    application, user, _, _ = guarded_app
    assert request(application, method="GET", url="/guard-sync").status_code == 401
    assert request(
        application, method="GET", url="/guard-sync", headers=headers(user)
    ).json() == {"ok": True}
    schema = application.openapi()["paths"]["/guard/{item_id}"]["post"]
    assert {p["name"] for p in schema["parameters"]} == {
        "item_id",
        "limit",
        "Authorization",
    }
    assert schema["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GuardBody"
    }
