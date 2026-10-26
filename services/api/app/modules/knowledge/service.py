import asyncio
import logging

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.core.pagination import PageParams
from app.infrastructure.database import session

from .repository import KnowledgeRepository
from . import storage
from .schemas import (KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBasePage, KnowledgeBaseUpdate, KnowledgeDocumentSave, KnowledgeDocumentOut)


async def create_knowledge_base(
    owner_id: int, body: KnowledgeBaseCreate
) -> KnowledgeBaseOut:
    """创建知识库并返回结果。"""
    async with session.transaction() as conn:
        record = await KnowledgeRepository(conn).create(owner_id, body.name, body.description)
        # 把数据库对象转换为接口响应数据
        return KnowledgeBaseOut.model_validate(record)


async def list_knowledge_bases(
    owner_id: int, params: PageParams, q: str = ""
) -> KnowledgeBasePage:
    """查询知识库分页。"""
    async with session.read_session() as conn:
        records, total = await KnowledgeRepository(conn).list_by_owner(
            owner_id, params, q.strip()
        )
        counts = await KnowledgeRepository(conn).document_counts([record.id for record in records])
        return KnowledgeBasePage(
            item=[KnowledgeBaseOut.model_validate(record).model_copy(update={"document_count": counts.get(record.id, 0)}) for record in records],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )


async def update_knowledge_base(
    owner_id: int, base_id: int, body: KnowledgeBaseUpdate
) -> KnowledgeBaseOut:
    """修改知识库。"""
    async with session.transaction() as conn:
        record = await KnowledgeRepository(conn).update(owner_id, base_id, body.name, body.description)
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        counts = await KnowledgeRepository(conn).document_counts([base_id])
        return KnowledgeBaseOut.model_validate(record).model_copy(update={"document_count": counts.get(base_id, 0)})


async def delete_knowledge_base(owner_id: int, base_id: int) -> None:
    """删除知识库及源文件。"""
    async with session.transaction() as conn:
        repository = KnowledgeRepository(conn)
        if not await repository.owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        keys = [row.storage_key for row in await repository.list_documents(base_id) if row.storage_key]
        if not await repository.delete(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
    for key in keys:
        await _remove_file(key)


async def list_documents(owner_id: int, base_id: int) -> list[KnowledgeDocumentOut]:
    """查询当前用户知识库中的文档。"""
    async with session.read_session() as conn:
        repository = KnowledgeRepository(conn)
        if not await repository.owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        return [KnowledgeDocumentOut.model_validate(row) for row in await repository.list_documents(base_id)]


async def get_document(owner_id: int, base_id: int, document_id: str) -> KnowledgeDocumentOut:
    """读取当前用户的在线文档。"""
    async with session.read_session() as conn:
        repository = KnowledgeRepository(conn)
        if not await repository.owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        record = await repository.get_document(base_id, document_id)
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "文档不存在", 404)
        return KnowledgeDocumentOut.model_validate(record)


async def save_document(owner_id: int, base_id: int, document_id: str, body: KnowledgeDocumentSave) -> KnowledgeDocumentOut:
    """自动保存文档，在事务提交后返回成功。"""
    async with session.transaction() as conn:
        return await save_document_in_transaction(conn, owner_id, base_id, document_id, body)


async def save_document_in_transaction(conn, owner_id: int, base_id: int, document_id: str, body: KnowledgeDocumentSave) -> KnowledgeDocumentOut:
    """在调用方事务内校验权限并写入文档，供跨模块归档使用。"""
    repository = KnowledgeRepository(conn)
    if not await repository.owns_base(owner_id, base_id):
        raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
    record = await repository.save_document(base_id, document_id, body.model_dump())
    if record is None:
        raise ApiError(ApiCode.NOT_FOUND, "文档不存在", 404)
    return KnowledgeDocumentOut.model_validate(record)


async def _remove_file(key: str) -> None:
    """清理已提交删除的源文件，失败时不恢复已删除记录。"""
    try:
        await asyncio.to_thread(storage.remove_file, key)
    except OSError:
        logging.getLogger(__name__).warning("知识库源文件清理失败")


async def delete_document(owner_id: int, base_id: int, document_id: str) -> None:
    """校验知识库归属并删除文档及源文件。"""
    async with session.transaction() as conn:
        repository = KnowledgeRepository(conn)
        if not await repository.owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        record = await repository.get_document(base_id, document_id)
        if record is None or not await repository.delete_document(base_id, document_id):
            raise ApiError(ApiCode.NOT_FOUND, "文档不存在", 404)
        key = record.storage_key
    if key:
        await _remove_file(key)


async def upload_document(owner_id: int, base_id: int, upload: storage.UploadSource) -> KnowledgeDocumentOut:
    """校验归属并保存上传文件，失败时清理本次文件。"""
    async with session.read_session() as conn:
        if not await KnowledgeRepository(conn).owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
    values = await storage.save_upload(owner_id, base_id, upload)
    try:
        async with session.transaction() as conn:
            repository = KnowledgeRepository(conn)
            if not await repository.owns_base(owner_id, base_id):
                raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
            record = await repository.create_upload(base_id, values)
            result = KnowledgeDocumentOut.model_validate(record)
        return result
    except BaseException:
        await _remove_file(values["storage_key"])
        raise


async def get_source_file(owner_id: int, base_id: int, document_id: str) -> tuple:
    """校验权限并定位上传的原始文件。"""
    async with session.read_session() as conn:
        repository = KnowledgeRepository(conn)
        if not await repository.owns_base(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        record = await repository.get_document(base_id, document_id)
        if record is None or record.source != "upload" or not record.storage_key:
            raise ApiError(ApiCode.NOT_FOUND, "源文件不存在", 404)
        path = storage.file_path(record.storage_key)
        if not path.is_file():
            raise ApiError(ApiCode.NOT_FOUND, "源文件不存在", 404)
        mime = "application/pdf" if record.file_type == "pdf" else "text/markdown; charset=utf-8"
        return path, record.original_name, mime
