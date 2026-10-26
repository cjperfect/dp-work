"""文档解析入口，PDF 在独立进程执行，文本通过 LangChain 加载。"""
import asyncio
import json
import sys
from tempfile import TemporaryDirectory

from ... import config


class ParseError(Exception):
    """可展示的文档解析错误。"""


def parse_txt(content: bytes):
    """通过 LangChain 解析 TXT。"""
    from .text import load_text
    return load_text(content, "txt", config.TEMP_DIR / "parsing")


def parse_markdown(content: bytes):
    """通过 LangChain 读取 Markdown，保留标题、列表、代码和表格。"""
    from .text import load_text
    return load_text(content, "md", config.TEMP_DIR / "parsing")


async def parse_document(content: bytes, file_type: str) -> dict:
    """按文档格式分发解析，文本读取不阻塞事件循环。"""
    if file_type == "pdf":
        return await parse_pdf(content)
    if file_type == "docx":
        return await parse_word(content)
    parser = {"txt": parse_txt, "md": parse_markdown}.get(file_type)
    if parser is None:
        raise ParseError("当前支持 TXT、Markdown、PDF 和 DOCX，旧版 DOC 暂不支持。")
    try:
        return await asyncio.to_thread(parser, content)
    except ValueError as cause:
        raise ParseError(str(cause)) from cause


async def parse_word(content: bytes) -> dict:
    """通过独立进程解析 DOCX。"""
    return await run_parser(content, "word", "Word")


async def parse_pdf(content: bytes) -> dict:
    """通过独立进程解析 PDF。"""
    return await run_parser(content, "pdf", "PDF")


async def run_parser(content: bytes, module: str, label: str) -> dict:
    """隔离耗时解析，超时或取消时终止进程并清理临时文件。"""
    temporary_root = config.TEMP_DIR / "parsing"
    temporary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = TemporaryDirectory(prefix=module + "-", dir=temporary_root)
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.knowledge.parsers." + module, temporary.name,
        cwd=config.SERVICE_ROOT, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(content), timeout=config.PDF_PARSE_TIMEOUT)
        if process.returncode or not output:
            raise ParseError(f"{label} 解析进程异常，请重试或拆分文件。")
        result = json.loads(output)
        if result.get("error"):
            raise ParseError(result["error"])
        return result
    except asyncio.TimeoutError as cause:
        raise ParseError(f"{label} 解析超时，请拆分文件后重试。") from cause
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await asyncio.to_thread(temporary.cleanup)
