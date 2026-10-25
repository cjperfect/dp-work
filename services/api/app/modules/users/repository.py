"""用户 ORM 查询；不创建 Session、不提交事务。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User


class UserRepository:
    """用户数据访问。"""
    def __init__(self, db_session: AsyncSession):
        """接收数据库会话。"""
        self.session = db_session

    async def find_by_username(self, username: str) -> User | None:
        """按用户名查询用户。"""
        return await self.session.scalar(select(User).where(User.username == username))

    async def find_by_id(self, user_id: int) -> User | None:
        """按用户 ID 查询用户。"""
        return await self.session.get(User, user_id)

    async def insert(
        self,
        *,
        username: str,
        password_hash: str,
        department: str,
        role: str,
    ) -> User | None:
        """新增用户，重名时跳过。"""
        statement = (
            insert(User)
            .values(
                username=username,
                password_hash=password_hash,
                department=department,
                role=role,
            )
            .on_conflict_do_nothing(index_elements=[User.username])
            .returning(User)
        )
        return (await self.session.scalars(statement)).one_or_none()

    async def list_public(self) -> list[dict]:
        """查询用户公开信息列表。"""
        result = await self.session.execute(
            select(
                User.id,
                User.username,
                User.department,
                User.role,
                User.status,
                User.created_at,
                User.updated_at,
            ).order_by(User.created_at)
        )
        return [dict(row) for row in result.mappings()]
