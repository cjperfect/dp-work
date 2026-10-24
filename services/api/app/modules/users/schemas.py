from pydantic import BaseModel


class UserCreateIn(BaseModel):
    username: str
    password: str
    display_name: str
    department: str
    role: str = "member"
