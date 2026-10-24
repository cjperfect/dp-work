"""共享 ORM 元数据；约束命名兼容现有 PostgreSQL 表。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "%(table_name)s_pkey",
            "uq": "%(table_name)s_%(column_0_N_name)s_key",
            "ix": "idx_%(table_name)s_%(column_0_N_name)s",
            "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
            "ck": "%(table_name)s_%(constraint_name)s_check",
        }
    )
