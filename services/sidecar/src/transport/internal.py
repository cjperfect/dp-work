"""供 API 服务调用的内部模型接口。"""
import secrets
from typing import Annotated, Literal
from fastapi import APIRouter, Header, HTTPException, Request, Query
from .. import config
from ..knowledge.parsers import dispatcher
from ..knowledge.parsers.pdf import MAX_SOURCE_BYTES
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


@router.post("/knowledge/parse", summary="解析 TXT、Markdown、PDF 或 DOCX 文档")
async def parse_document(request: Request, x_internal_token: Annotated[str | None, Header()] = None,
                         file_type: Annotated[Literal["pdf", "txt", "md", "docx"], Query()] = "pdf"):
    """接收源文件字节，返回解析正文，不启用 OCR。"""
    authorize(x_internal_token)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_SOURCE_BYTES:
            raise HTTPException(413, detail={"message": "文件不能超过 20 MB。"})
    if file_type == "pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(400, detail={"message": "文件内容不是有效 PDF。"})
    try:
        return await dispatcher.parse_document(bytes(content), file_type)
    except dispatcher.ParseError as cause:
        raise HTTPException(422, detail={"message": str(cause)}) from cause
