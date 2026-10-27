"""技能安装与卸载参数。"""
from typing import Literal
from pydantic import BaseModel, Field

AgentCode = Literal["general", "product"]


class InstallInput(BaseModel):
    agent_code: AgentCode
    source: str = Field(min_length=1, max_length=512)


class UninstallInput(BaseModel):
    agent_code: AgentCode
    skill_id: str = Field(min_length=1, max_length=256)




class DescriptionsInput(BaseModel):
    skill_ids: list[str] = Field(max_length=24)
