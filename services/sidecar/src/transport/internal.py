"""供 API 服务调用的内部模型接口。"""
import secrets
from typing import Annotated
from fastapi import APIRouter, Header, HTTPException
from .. import config
from ..meetings.minutes import generate
from ..meetings.schemas import MinutesInput, MinutesOutput
from ..providers.llm.schemas import ModelError

router = APIRouter(prefix="/internal", tags=["internal"])


def authorize(value: str | None):
    """验证 API 与 Sidecar 的服务凭证。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise HTTPException(503, detail={"code": "INTERNAL_NOT_CONFIGURED", "message": "Sidecar 内部服务凭证尚未配置。"})
    if not value or not secrets.compare_digest(value, config.SIDECAR_INTERNAL_TOKEN):
        raise HTTPException(401, detail={"code": "INTERNAL_UNAUTHORIZED", "message": "无效的内部服务凭证。"})


@router.post("/meetings/minutes/generate", response_model=MinutesOutput)
async def generate_minutes(body: MinutesInput, x_internal_token: Annotated[str | None, Header()] = None):
    """生成会议纪要，密钥和模型调用仅在服务端处理。"""
    authorize(x_internal_token)
    try:
        return await generate(body)
    except ModelError as cause:
        raise HTTPException(502, detail={"code": cause.code, "message": str(cause)}) from cause
