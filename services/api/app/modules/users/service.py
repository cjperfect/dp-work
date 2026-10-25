"""用户业务入口；其他模块通过此文件使用用户能力。"""

from app.core.security import hash_password
from app.infrastructure.database import session

from .exceptions import UsernameExistsError
from .models import User
from .repository import UserRepository


async def find_by_username(username: str) -> User | None:
    """按用户名查询用户。"""
    async with session.read_session() as conn:
        return await UserRepository(conn).find_by_username(username)


async def find_by_id(user_id: int) -> User | None:
    """按用户 ID 查询用户。"""
    async with session.read_session() as conn:
        return await UserRepository(conn).find_by_id(user_id)


async def find_by_subject(subject: object, version: object) -> User | None:
    """根据令牌身份查询用户。"""
    if type(version) is not int or version != 2:
        return None
    if not isinstance(subject, str) or not subject:
        return None
    if not subject.isascii() or not subject.isdecimal() or len(subject) > 19:
        return None
    user_id = int(subject)
    if user_id < 1 or user_id > 9_223_372_036_854_775_807:
        return None
    return await find_by_id(user_id)


async def list_users() -> list[dict]:
    """获取用户列表。"""
    async with session.read_session() as conn:
        return await UserRepository(conn).list_public()


async def create_user(
    username: str,
    password: str,
    department: str,
    role: str = "member",
    *,
    allow_existing: bool = False,
) -> User:
    """创建用户。"""
    password_hash = hash_password(password)
    async with session.transaction() as conn:
        repository = UserRepository(conn)
        user = await repository.insert(
            username=username,
            password_hash=password_hash,
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
