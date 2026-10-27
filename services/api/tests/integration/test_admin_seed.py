"""真实数据库验证默认管理员、密码哈希与重启幂等。"""

import asyncio

from src.core.security import hash_password, verify_password
from src.infrastructure.database import session
from src.modules.auth import service as auth_service
from src.modules.users import bootstrap, service
from src.modules.users.models import User
from sqlalchemy import delete, update


def test_default_admin_and_existing_password_are_preserved(monkeypatch):
    monkeypatch.setattr(bootstrap.config, "BOOTSTRAP_ADMIN_ENABLED", True)
    monkeypatch.setattr(bootstrap.config, "BOOTSTRAP_ADMIN_USERNAME", "chenjiang")
    monkeypatch.setattr(bootstrap.config, "BOOTSTRAP_ADMIN_PASSWORD", "chenjiang")

    async def case():
        await session.init_db()
        try:
            await bootstrap.ensure_initial_admin()
            user = await service.find_by_username("chenjiang")
            assert user.role == "admin"
            assert user.password_hash != "chenjiang"
            assert verify_password("chenjiang", user.password_hash)
            assert (await auth_service.login("chenjiang", "chenjiang"))["user"][
                "role"
            ] == "admin"
            await bootstrap.ensure_initial_admin()
            assert (
                await service.find_by_username("chenjiang")
            ).password_hash == user.password_hash
            async with session.transaction() as db_session:
                await db_session.execute(
                    update(User)
                    .where(User.username == "chenjiang")
                    .values(password_hash=hash_password("changed-password"))
                )
            await bootstrap.ensure_initial_admin()
            assert verify_password(
                "changed-password",
                (await service.find_by_username("chenjiang")).password_hash,
            )
        finally:
            async with session.transaction() as db_session:
                await db_session.execute(
                    delete(User).where(User.username == "chenjiang")
                )
            await session.close_db()

    asyncio.run(case())
