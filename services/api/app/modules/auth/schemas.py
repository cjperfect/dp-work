"""认证 HTTP 请求协议。"""

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    token: str


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=2, max_length=32, pattern=r"^\S+$")
    password: str = Field(min_length=8, max_length=128)
