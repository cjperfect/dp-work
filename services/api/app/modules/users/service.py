"""用户业务入口；其他模块通过此文件使用用户能力。"""

from app.core.security import hash_password
from app.infrastructure.database import session

from .exceptions import UsernameExistsError
from .models import User
from .repository import UserRepository


async def find_by_username(username: str) -> User | None:
    async with session.read_session() as conn:
        return await UserRepository(conn).find_by_username(username)


async def find_by_id(user_id: str) -> User | None:
    async with session.read_session() as conn:
        return await UserRepository(conn).find_by_id(user_id)


async def list_users() -> list[dict]:
    async with session.read_session() as conn:
        return await UserRepository(conn).list_public()


async def create_user(
    username: str,
    password: str,
    display_name: str,
    department: str,
    role: str = "member",
    *,
    allow_existing: bool = False,
) -> User:
    password_hash = hash_password(password)
    async with session.transaction() as conn:
        repository = UserRepository(conn)
        user = await repository.insert(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            department=department,
            role=role,
        )
        if user is not None:
            return user
        if allow_existing:
            existing = await repository.find_by_username(username)
            if existing is not None:
                return existing
        raise UsernameExistsError(username)
