"""真实数据库验证旧哈希登录升级，及并发改密后的比较更新保护。"""

import asyncio
from uuid import uuid4
from sqlalchemy import delete, update
from src.core.security import hash_password, verify_password
from src.infrastructure.database import session
from src.modules.auth import service as auth
from src.modules.users import service as users
from src.modules.users.models import User
from tests.unit.test_passwords import legacy


def test_legacy_login_upgrades_without_overwriting_changed_password():
    async def run():
        await session.init_db()
        user = await users.create_user(
            "upgrade-" + uuid4().hex, "fixture-password", "product"
        )
        old = legacy("fixture-password")
        try:
            async with session.transaction() as db:
                await db.execute(
                    update(User).where(User.id == user.id).values(password_hash=old)
                )
            result = await auth.login(user.username, "fixture-password")
            assert result["user"]["id"] == user.id
            current = await users.find_by_id(user.id)
            assert current.password_hash.startswith("$argon2id$")
            assert verify_password("fixture-password", current.password_hash)
            reset = hash_password("changed-password")
            async with session.transaction() as db:
                await db.execute(
                    update(User).where(User.id == user.id).values(password_hash=reset)
                )
            await users.upgrade_password_hash(
                user.id, old, hash_password("fixture-password")
            )
            assert (await users.find_by_id(user.id)).password_hash == reset
        finally:
            async with session.transaction() as db:
                await db.execute(delete(User).where(User.id == user.id))
            await session.close_db()

    asyncio.run(run())
