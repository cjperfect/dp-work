"""通用数据库分页查询。"""

from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams

T = TypeVar("T")


async def paginate(
    db: AsyncSession,
    statement: Select[tuple[T]],
    params: PageParams,
    total: int | None = None,
) -> tuple[list[T], int]:
    """统计并分页查询单实体数据。"""
    if total is None:
        count_query = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int(await db.scalar(count_query) or 0)
    records = await db.scalars(statement.offset(params.offset).limit(params.page_size))
    return list(records.all()), total
