"""用户 ORM 查询；不创建 Session、不提交事务。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User


class UserRepository:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session

    async def find_by_username(self, username: str) -> User | None:
        return await self.session.scalar(select(User).where(User.username == username))

    async def find_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def insert(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str,
        department: str,
        role: str,
    ) -> User | None:
        statement = (
            insert(User)
            .values(
                id=f"u-{username}",
                username=username,
                password_hash=password_hash,
                display_name=display_name,
                department=department,
                role=role,
            )
            .on_conflict_do_nothing(index_elements=[User.username])
            .returning(User)
        )
        return (await self.session.scalars(statement)).one_or_none()

    async def list_public(self) -> list[dict]:
        result = await self.session.execute(
            select(
                User.id,
                User.username,
                User.display_name,
                User.department,
                User.role,
                User.status,
            ).order_by(User.created_at)
        )
        return [dict(row) for row in result.mappings()]
