"""认证 HTTP 请求协议。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class LoginIn(BaseModel):
    """登录请求参数。"""
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    model_config = ConfigDict(extra="forbid")

    encrypted_password: str = Field(min_length=1, repr=False)


class RefreshIn(BaseModel):
    """令牌刷新参数。"""
    token: str


class RegisterIn(LoginIn):
    """注册请求参数。"""
    model_config = ConfigDict(extra="forbid")

    department: str = Field(default="unassigned", min_length=1, max_length=32)
