"""技能管理适配。"""
import asyncio
import base64
import binascii
from typing import Literal
from pydantic import BaseModel, Field
from ..types import OperationError


class SkillsAgent(BaseModel):
    agent_code: Literal["general", "product", "ui"]


class SkillsSearch(BaseModel):
    query: str = Field(default="", max_length=200)


class SkillsDescriptions(BaseModel):
    skill_ids: list[str] = Field(max_length=24)


class SkillInstall(SkillsAgent):
    source: str = Field(min_length=1, max_length=512)


class SkillUpload(SkillsAgent):
    filename: str = Field(min_length=1, max_length=256)
    content_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)


class SkillUninstall(SkillsAgent):
    skill_id: str = Field(min_length=1, max_length=256)


async def skill_operation(operation, params, state):
    """将技能管理错误转换为可展示的业务错误。"""
    from ...skills import service
    try:
        if operation == "descriptions":
            from ...skills.descriptions import descriptions
            body = SkillsDescriptions.model_validate(params)
            return {"items": await descriptions(body.skill_ids)}
        if operation == "search":
            body = SkillsSearch.model_validate(params)
            return {"items": await service.search(body.query)}
        if operation == "upload":
            body = SkillUpload.model_validate(params)
            try:
                content = base64.b64decode(body.content_base64, validate=True)
            except (ValueError, binascii.Error) as cause:
                raise service.SkillError("技能文件编码无效。") from cause
            return await service.upload(body.agent_code, body.filename, content)
        body = (SkillInstall if operation == "install" else SkillUninstall if operation == "uninstall" else SkillsAgent).model_validate(params)
        if operation == "list":
            return {"items": await service.file_operation(service.installed, body.agent_code)}
        if operation == "install":
            return await service.install(body.agent_code, body.source)
        return await service.uninstall(body.agent_code, body.skill_id)
    except service.SkillError as cause:
        raise OperationError(cause.status, str(cause)) from cause

