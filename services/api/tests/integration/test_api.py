"""API 架构验收测试：统一响应协议 + 认证守卫 + 异常过滤器（docs/api-architecture.md §10）。

覆盖场景：登录 / 刷新 / me、无 token / 错 token / 越权 / 参数校验失败 / 未知路由 /
批量写入幂等 / 纪要未生成。

执行方式：每个测试内用 asyncio.run 在**单一事件循环**中完成
init_db → 建用户 → httpx 直测 app → 清理 → close_db，
每个测试使用独立的异步引擎，避免跨事件循环复用。
"""

from __future__ import annotations

import asyncio

from app.infrastructure.database import session as db
from app.main import app
from app.modules.meetings.models import TranscriptSegment
from app.modules.users.models import User
from app.modules.users.service import create_user
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

MEMBER = {
    "username": "tester_arch",
    "password": "pass1234",
    "display_name": "测试员",
    "department": "product",
    "role": "member",
}
ADMIN = {
    "username": "tadmin_arch",
    "password": "admin1234",
    "display_name": "管理员",
    "department": "product",
    "role": "admin",
}


async def setup_client() -> AsyncClient:
    await db.init_db()
    await create_user(**MEMBER, allow_existing=True)
    await create_user(**ADMIN, allow_existing=True)
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    await client.__aenter__()
    return client


async def teardown(client: AsyncClient) -> None:
    await client.__aexit__(None, None, None)
    async with db.transaction() as db_session:
        await db_session.execute(
            delete(User).where(
                User.username.in_([MEMBER["username"], ADMIN["username"]])
            )
        )
        await db_session.execute(
            delete(TranscriptSegment).where(
                TranscriptSegment.meeting_id == "api-arch-test"
            )
        )
    await db.close_db()


async def login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert "token" in body["data"]
    return body["data"]["token"]


def run(case):  # type: ignore[no-untyped-def]
    asyncio.run(case())


# ---------- 公开接口 ----------


def test_health_public() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"ok": True, "db": "up"}
        finally:
            await teardown(client)

    run(case)


# ---------- 认证 ----------


def test_login_ok_and_me() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            token = await login(client, MEMBER["username"], MEMBER["password"])
            r = await client.get(
                "/api/v1/auth/users/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert r.status_code == 200
            body = r.json()
            assert body["code"] == 0
            assert body["data"]["username"] == MEMBER["username"]
            assert body["data"]["department"] == MEMBER["department"]
            assert "password_hash" not in body["data"]
        finally:
            await teardown(client)

    run(case)


def test_login_bad_credentials() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.post(
                "/api/v1/auth/login", json={"username": "tester", "password": "wrong"}
            )
            assert r.status_code == 401
            body = r.json()
            assert body["code"] == 2004
            assert body["data"] is None
        finally:
            await teardown(client)

    run(case)


def test_refresh() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            token = await login(client, MEMBER["username"], MEMBER["password"])
            r = await client.post("/api/v1/auth/refresh", json={"token": token})
            assert r.status_code == 200
            assert r.json()["data"]["token"]
        finally:
            await teardown(client)

    run(case)


def test_refresh_bad_token() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.post("/api/v1/auth/refresh", json={"token": "not-a-jwt"})
            assert r.status_code == 401
            assert r.json()["code"] == 2002
        finally:
            await teardown(client)

    run(case)


# ---------- 守卫 ----------


def test_segments_requires_auth() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.post(
                "/api/v1/segments", json={"meeting_id": "m1", "segments": []}
            )
            assert r.status_code == 401
            body = r.json()
            assert body["code"] == 2001
            assert body["data"] is None
        finally:
            await teardown(client)

    run(case)


def test_segments_bad_token() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.post(
                "/api/v1/segments",
                json={"meeting_id": "m1", "segments": []},
                headers={"Authorization": "Bearer invalid.token.here"},
            )
            assert r.status_code == 401
            assert r.json()["code"] == 2002
        finally:
            await teardown(client)

    run(case)


def test_admin_required() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            member_token = await login(client, MEMBER["username"], MEMBER["password"])
            r = await client.get(
                "/api/v1/users", headers={"Authorization": f"Bearer {member_token}"}
            )
            assert r.status_code == 403
            assert r.json()["code"] == 2003

            admin_token = await login(client, ADMIN["username"], ADMIN["password"])
            r = await client.get(
                "/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert r.status_code == 200
            assert r.json()["code"] == 0
        finally:
            await teardown(client)

    run(case)


# ---------- 统一响应与异常 ----------


def test_segments_validation_error() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            token = await login(client, MEMBER["username"], MEMBER["password"])
            r = await client.post(
                "/api/v1/segments",
                json={
                    "meeting_id": "m1",
                    "segments": [{"seq": "not-int", "text": 123}],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 422
            body = r.json()
            assert body["code"] == 1002
            assert isinstance(body["data"], list)  # 字段级明细
        finally:
            await teardown(client)

    run(case)


def test_segments_write_and_idempotent() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            token = await login(client, MEMBER["username"], MEMBER["password"])
            meeting = "api-arch-test"
            payload = {
                "meeting_id": meeting,
                "segments": [
                    {
                        "id": f"{meeting}#0",
                        "seq": 0,
                        "speaker": "王明",
                        "text": "架构验收第一条",
                    },
                    {
                        "id": f"{meeting}#1",
                        "seq": 1,
                        "speaker": "李静",
                        "text": "架构验收第二条",
                    },
                ],
            }
            headers = {"Authorization": f"Bearer {token}"}
            r = await client.post("/api/v1/segments", json=payload, headers=headers)
            assert r.status_code == 200
            assert r.json()["data"] == {"written": 2, "ignored": 0}

            r2 = await client.post(
                "/api/v1/segments",
                json={"meeting_id": meeting, "segments": [payload["segments"][0]]},
                headers=headers,
            )
            assert r2.status_code == 200
            assert r2.json()["data"] == {"written": 0, "ignored": 1}
        finally:
            await teardown(client)

    run(case)


def test_minutes_not_ready() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            token = await login(client, MEMBER["username"], MEMBER["password"])
            r = await client.get(
                "/api/v1/meetings/does-not-exist/minutes",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 404
            assert r.json()["code"] == 3002
        finally:
            await teardown(client)

    run(case)


def test_unknown_route_unified_format() -> None:
    async def case() -> None:
        client = await setup_client()
        try:
            r = await client.get("/api/v1/no-such-route")
            assert r.status_code == 404
            body = r.json()
            assert body["code"] == 1003
            assert body["data"] is None
        finally:
            await teardown(client)

    run(case)
