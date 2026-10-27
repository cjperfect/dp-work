from pydantic import BaseModel


class UserCreateIn(BaseModel):
    """用户创建参数。"""
    username: str
    password: str
    department: str
    role: str = "member"
