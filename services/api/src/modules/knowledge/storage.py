"""知识库源文件的本地存储。"""
import asyncio
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from typing import Protocol

from src.core.exceptions import ApiError
from src.core.responses import ApiCode

REPO_ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = Path(os.environ.get("DP_DATA_DIR") or REPO_ROOT / ".dp-work/data")
MAX_FILE_SIZE = 20 * 1024 * 1024


class UploadSource(Protocol):
    """上传数据流，不绑定 HTTP 框架。"""
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


def file_path(key: str) -> Path:
    """解析内部文件标识并限定存储范围。"""
    root = (DATA_DIR / "knowledge").resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("无效的源文件路径")
    return path


async def save_upload(owner_id: int, base_id: int, upload: UploadSource) -> dict:
    """流式保存 TXT、Markdown、PDF 或 Word，校验大小、编码与文件格式。"""
    filename = (upload.filename or "").replace("\\", "/").split("/")[-1].strip()
    extension = Path(filename).suffix.lower().lstrip(".")
    if not filename or "\x00" in filename or extension not in ("txt", "md", "markdown", "pdf", "doc", "docx"):
        raise ApiError(ApiCode.PARAM_ERROR, "仅支持上传 TXT、Markdown、PDF 和 Word 文件。", 400)
    document_id = f"upload-{uuid4()}"
    key = f"{owner_id}/{base_id}/{document_id}.{extension}"
    target = file_path(key)
    temporary_dir = DATA_DIR.parent / "temp/uploads"
    temporary_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = None
    try:
        size = 0
        with NamedTemporaryFile(dir=temporary_dir, prefix=".upload-", delete=False) as stream:
            staging = Path(stream.name)
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise ApiError(ApiCode.PARAM_ERROR, "单个文件不能超过 20 MB。", 413)
                await asyncio.to_thread(stream.write, chunk)
            stream.flush()
            await asyncio.to_thread(os.fsync, stream.fileno())
        if not size:
            raise ApiError(ApiCode.PARAM_ERROR, "不能上传空文件。", 400)
        content = ""
        if extension in ("txt", "md", "markdown"):
            try:
                content = await asyncio.to_thread(staging.read_text, encoding="utf-8-sig")
            except UnicodeDecodeError as cause:
                raise ApiError(ApiCode.PARAM_ERROR, "文本文件请使用 UTF-8 编码。", 400) from cause
        elif extension == "pdf":
            with staging.open("rb") as stream:
                if not stream.read(5) == b"%PDF-":
                    raise ApiError(ApiCode.PARAM_ERROR, "文件内容不是有效的 PDF 格式。", 400)
        elif extension in ("doc", "docx"):
            with staging.open("rb") as stream:
                signature = stream.read(8)
            expected = b"PK\x03\x04" if extension == "docx" else b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            if not signature.startswith(expected):
                raise ApiError(ApiCode.PARAM_ERROR, "文件内容不是有效的 Word 格式。", 400)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        await asyncio.to_thread(os.replace, staging, target)
        return dict(id=document_id, title=Path(filename).stem, source="upload", file_type="md" if extension == "markdown" else extension,
                    original_name=filename, byte_size=size, content=content, storage_key=key)
    finally:
        await upload.close()
        if staging:
            staging.unlink(missing_ok=True)


def remove_file(key: str) -> None:
    """删除内部记录对应的源文件。"""
    file_path(key).unlink(missing_ok=True)
