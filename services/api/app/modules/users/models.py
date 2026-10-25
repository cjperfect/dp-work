"""用户 ORM 模型；对外协议由 schemas 单独定义。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    FetchedValue,
    Identity,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base

from .constants import STATUS_ACTIVE


class User(Base):
    """用户表模型。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default=text("'member'"))
    status: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )

    @property
    def is_active(self) -> bool:
        """判断账号是否正常。"""
        return self.status == STATUS_ACTIVE

    def to_public(self) -> dict[str, Any]:
        """获取用户公开信息。"""
        return {
            "id": self.id,
            "username": self.username,
            "department": self.department,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
