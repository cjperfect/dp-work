"""通用分页参数和响应。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """分页查询参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数，最多 100")

    @property
    def offset(self) -> int:
        """获取查询偏移量。"""
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    """分页响应数据。"""

    item: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

