from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, File, UploadFile
from fastapi.responses import FileResponse

from src.core.pagination import PageParams
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User

from . import service, parsing, rag
from .events import router as events_router
from .schemas import (KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBasePage, KnowledgeBaseUpdate, KnowledgeDocumentSave, KnowledgeDocumentRename, KnowledgeDocumentOut, ParsedDocumentSave, VectorizeDocument)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])
router.include_router(events_router)


@router.post(
    "",
    response_model=ApiResponse[KnowledgeBaseOut],
    status_code=200,
    summary="新增知识库",
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KnowledgeBaseOut]:
    """处理新增知识库请求。"""
    return ok(await service.create_knowledge_base(user.id, body), message="知识库创建成功")


@router.get(
    "",
    response_model=ApiResponse[KnowledgeBasePage],
    summary="查询知识库列表",
)
async def list_knowledge_bases(
    user: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[PageParams, Depends()],
    q: Annotated[str, Query(description="按名称或描述搜索")] = "",
) -> ApiResponse[KnowledgeBasePage]:
    """查询当前用户的知识库。"""
    return ok(await service.list_knowledge_bases(user.id, pagination, q))


@router.put(
    "/{base_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="修改知识库",
)
async def update_knowledge_base(
    base_id: Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)],
    body: KnowledgeBaseUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KnowledgeBaseOut]:
    """处理修改知识库请求。"""
    return ok(await service.update_knowledge_base(user.id, base_id, body), message="知识库修改成功")


@router.delete(
    "/{base_id}",
    response_model=ApiResponse[None],
    summary="删除知识库",
)
async def delete_knowledge_base(
    base_id: Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """处理删除知识库请求。"""
    await service.delete_knowledge_base(user.id, base_id)
    return ok(message="知识库删除成功")


BaseId = Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)]
DocumentId = Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/{base_id}/documents", response_model=ApiResponse[list[KnowledgeDocumentOut]], summary="查询在线文档")
async def list_documents(base_id: BaseId, user: CurrentUser) -> ApiResponse[list[KnowledgeDocumentOut]]:
    """返回知识库的在线文档列表。"""
    return ok(await service.list_documents(user.id, base_id))


@router.get("/{base_id}/documents/{document_id}", response_model=ApiResponse[KnowledgeDocumentOut], summary="读取在线文档")
async def get_document(base_id: BaseId, document_id: DocumentId, user: CurrentUser) -> ApiResponse[KnowledgeDocumentOut]:
    """返回指定文档的标题、正文和富文本块。"""
    return ok(await service.get_document(user.id, base_id, document_id))


@router.put("/{base_id}/documents/{document_id}", response_model=ApiResponse[KnowledgeDocumentOut], summary="自动保存在线文档")
async def save_document(base_id: BaseId, document_id: DocumentId, body: KnowledgeDocumentSave, user: CurrentUser) -> ApiResponse[KnowledgeDocumentOut]:
    """幂等创建或更新在线文档。"""
    return ok(await service.save_document(user.id, base_id, document_id, body), message="文档已保存")


@router.patch("/{base_id}/documents/{document_id}/title", response_model=ApiResponse[KnowledgeDocumentOut], summary="修改在线文档标题")
async def rename_document(base_id: BaseId, document_id: DocumentId, body: KnowledgeDocumentRename, user: CurrentUser):
    """只保存标题，保留当前正文。"""
    return ok(await service.rename_document(user.id, base_id, document_id, body.title), message="标题已保存")


@router.delete("/{base_id}/documents/{document_id}", response_model=ApiResponse[None], summary="删除在线文档")
async def delete_document(base_id: BaseId, document_id: DocumentId, user: CurrentUser) -> ApiResponse[None]:
    """删除当前用户知识库中的文档。"""
    await service.delete_document(user.id, base_id, document_id)
    return ok(message="文档已删除")


@router.post("/{base_id}/documents/upload", response_model=ApiResponse[KnowledgeDocumentOut], summary="上传 TXT、Markdown、PDF 或 Word")
async def upload_document(base_id: BaseId, file: Annotated[UploadFile, File(description="TXT、Markdown、PDF 或 Word，最大 20 MB")], user: CurrentUser):
    """保存文件并返回列表所需的文档信息。"""
    return ok(await service.upload_document(user.id, base_id, file), message="文件上传成功")


@router.get("/{base_id}/documents/{document_id}/file", response_class=FileResponse, summary="读取上传源文件")
async def get_source_file(base_id: BaseId, document_id: DocumentId, user: CurrentUser):
    """鉴权后提供源文件下载或预览。"""
    path, filename, mime = await service.get_source_file(user.id, base_id, document_id)
    return FileResponse(path, filename=filename, media_type=mime)


@router.post("/{base_id}/documents/{document_id}/parse", response_model=ApiResponse[KnowledgeDocumentOut], summary="提交文档解析任务")
async def parse_document(base_id: BaseId, document_id: DocumentId, user: CurrentUser):
    """提交异步解析，查询文档接口获取进度与 Markdown 结果。"""
    return ok(await parsing.request_parse(user.id, base_id, document_id), message="解析任务已提交")


@router.put("/{base_id}/documents/{document_id}/parsed", response_model=ApiResponse[KnowledgeDocumentOut], summary="自动保存解析后文档")
async def save_parsed_document(base_id: BaseId, document_id: DocumentId, body: ParsedDocumentSave, user: CurrentUser):
    """保存人工调整后的正文和富文本块。"""
    return ok(await parsing.save_parsed(user.id, base_id, document_id, body), message="解析文档已保存")


@router.post("/{base_id}/documents/{document_id}/vectorize", response_model=ApiResponse[KnowledgeDocumentOut], summary="提交文档向量化任务")
async def vectorize_document(base_id: BaseId, document_id: DocumentId, body: VectorizeDocument, user: CurrentUser):
    """按解析版本提交父子分块向量化任务。"""
    return ok(await rag.enqueue(user.id, base_id, document_id, body.expected_parsed_at), message="向量任务已提交")
