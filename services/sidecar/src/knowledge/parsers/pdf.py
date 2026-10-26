"""使用 PyMuPDFLoader 提取 PDF 正文和 Markdown 表格，不启用 OCR。"""
import contextlib
import io
import json
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PAGES = 200


def parse_pdf(content: bytes, temp_dir: Path) -> dict:
    """提取逐页正文，保留页码并清理无效控制字符。"""
    import pymupdf
    from langchain_community.document_loaders.pdf import PyMuPDFLoader

    if len(content) > MAX_SOURCE_BYTES or not content.startswith(b"%PDF-"):
        raise ValueError("仅支持不超过 20 MB 的有效 PDF 文件。")
    temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile(suffix=".pdf", dir=temp_dir) as source:
        source.write(content)
        source.flush()
        with pymupdf.open(source.name) as document:
            if document.needs_pass:
                raise ValueError("暂不支持加密 PDF，请解密后上传。")
            if len(document) > MAX_PAGES:
                raise ValueError("单个 PDF 暂时最多支持 200 页。")
        loader = PyMuPDFLoader(source.name, mode="page", extract_images=False, extract_tables="markdown")
        pages = []
        output_size = 0
        for document in loader.lazy_load():
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", document.page_content).replace("\r\n", "\n").strip()
            output_size += len(text.encode("utf-8"))
            if output_size > MAX_OUTPUT_BYTES:
                raise ValueError("PDF 提取内容过大，请拆分文档后重试。")
            pages.append({"page": document.metadata["page"], "page_number": document.metadata["page"] + 1,
                          "content": text})
        text = "\n\n---\n\n".join(page["content"] for page in pages if page["content"])
        if not text:
            raise ValueError("PDF 未提取到文字，扫描件或图片内容暂不支持识别。")
        return {"status": "parsed", "content": text, "metadata": pages, "parser": "pymupdf"}


if __name__ == "__main__":
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = parse_pdf(sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1), Path(sys.argv[1]))
    except ValueError as cause:
        result = {"error": str(cause)}
    except Exception:
        result = {"error": "PDF 解析失败，请检查文件是否损坏，或重试。"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
