"""使用 LangChain TextLoader 读取 TXT 和 Markdown，保留正文格式。"""
import re
from tempfile import NamedTemporaryFile
from pathlib import Path

from langchain_community.document_loaders.text import TextLoader

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def load_text(content: bytes, file_type: str, temp_dir: Path) -> dict:
    """按 UTF-8 读取文档，仅清理控制字符并统一换行。"""
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("单个文件不能超过 20 MB。")
    temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile(suffix="." + file_type, dir=temp_dir) as source:
        source.write(content)
        source.flush()
        try:
            document = TextLoader(source.name, encoding="utf-8-sig", autodetect_encoding=False).load()[0]
        except RuntimeError as cause:
            raise ValueError("文本文件请使用 UTF-8 编码。") from cause
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", document.page_content)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        raise ValueError("文档正文为空，请添加内容后重试。")
    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("文档正文过大，请拆分后重试。")
    result = {"status": "parsed", "content": text, "metadata": [{"format": file_type}], "parser": "langchain-text"}
    if file_type == "txt":
        # TXT 的星号、井号等符号按普通文字显示，不当作 Markdown 标记。
        result["blocks"] = [{"type": "paragraph", "content": [{"type": "text", "text": text, "styles": {}}]}]
    return result
