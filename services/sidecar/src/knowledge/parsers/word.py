"""使用 python-docx 按文档顺序提取 DOCX 正文和表格。"""
import io
import json
import re
import sys
import zipfile

from docx import Document
from docx.table import Table
from docx.text.run import Run

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_ELEMENTS = 20000


def clean(text: str) -> str:
    """清理无法存入正文的控制字符。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).replace("\r\n", "\n")


def markdown_text(text: str) -> str:
    """转义正文中的 Markdown 标记。"""
    return re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", text)


def paragraph_content(paragraph) -> tuple[list[dict], str]:
    """保留正文顺序及基础行内样式，包含超链接中的文字。"""
    content, markdown = [], []
    for item in paragraph.iter_inner_content():
        runs = [item] if isinstance(item, Run) else item.runs
        for run in runs:
            text = clean(run.text)
            if not text:
                continue
            styles = {key: True for key, enabled in [("bold", run.bold), ("italic", run.italic), ("underline", run.underline)] if enabled}
            content.append({"type": "text", "text": text, "styles": styles})
            rendered = markdown_text(text)
            if run.bold:
                rendered = "**" + rendered + "**"
            if run.italic:
                rendered = "*" + rendered + "*"
            markdown.append(rendered)
    return content, "".join(markdown)


def list_kind(paragraph, document) -> tuple[str | None, int]:
    """读取列表编号定义，区分有序、无序及缩进层级。"""
    properties = [paragraph._p.pPr]
    style = paragraph.style
    if style is not None:
        properties.append(style.element.pPr)
    for props in properties:
        if props is None or props.numPr is None or props.numPr.numId is None:
            continue
        num_id = props.numPr.numId.val
        if num_id == 0:
            return None, 0
        level = min(int(props.numPr.ilvl.val) if props.numPr.ilvl is not None else 0, 8)
        root = document.part.numbering_part.element
        abstracts = root.xpath(f'./w:num[@w:numId="{num_id}"]/w:abstractNumId/@w:val')
        if abstracts:
            formats = root.xpath(f'./w:abstractNum[@w:abstractNumId="{abstracts[0]}"]/w:lvl[@w:ilvl="{level}"]/w:numFmt/@w:val')
            if formats:
                return ("bulletListItem" if formats[0] == "bullet" else "numberedListItem"), level
    name = style.style_id if style is not None else ""
    if name.startswith("ListBullet"):
        return "bulletListItem", 0
    if name.startswith("ListNumber"):
        return "numberedListItem", 0
    return None, 0


def parse_word(content: bytes) -> dict:
    """提取 DOCX 为 Markdown 与 BlockNote 块，不执行图片识别。"""
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Word 文件不能超过 20 MB。")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > MAX_UNPACKED_BYTES:
                raise ValueError("Word 解压后内容过大，请拆分文档。")
            if "word/document.xml" not in archive.namelist():
                raise ValueError("文件不是有效的 DOCX 文档。")
        document = Document(io.BytesIO(content))
    except (zipfile.BadZipFile, KeyError) as cause:
        raise ValueError("DOCX 文件已损坏，或不是有效的 Word 文档。") from cause
    blocks, parts, metadata, stack = [], [], [], []
    output_bytes = 0
    for index, item in enumerate(document.iter_inner_content()):
        if index >= MAX_ELEMENTS:
            raise ValueError("Word 文档内容过多，请拆分后重试。")
        if isinstance(item, Table):
            if len(item.rows) * len(item.columns) > MAX_ELEMENTS:
                raise ValueError("Word 表格过大，请拆分后重试。")
            rows = [[clean(cell.text) for cell in row.cells] for row in item.rows]
            if not rows or not any(cell.strip() for row in rows for cell in row):
                continue
            lines = ["| " + " | ".join(markdown_text(cell).replace("\n", "<br>") for cell in row) + " |" for row in rows]
            lines.insert(1, "| " + " | ".join("---" for _ in rows[0]) + " |")
            markdown = "\n".join(lines)
            block = {"type": "table", "content": {"type": "tableContent", "rows": [{"cells": row} for row in rows]}}
            stack = []
        else:
            inline, markdown = paragraph_content(item)
            if not markdown.strip():
                continue
            style_id = item.style.style_id if item.style is not None else ""
            heading = re.fullmatch(r"Heading([1-9])", style_id)
            kind, level = list_kind(item, document)
            block = {"type": "paragraph", "content": inline}
            if heading or style_id == "Title":
                depth = min(int(heading[1]) if heading else 1, 3)
                block.update(type="heading", props={"level": depth})
                markdown = "#" * depth + " " + markdown
                stack = []
            elif kind:
                block["type"] = kind
                markdown = "  " * level + ("- " if kind == "bulletListItem" else "1. ") + markdown
                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    stack[-1][1].setdefault("children", []).append(block)
                else:
                    blocks.append(block)
                stack.append((level, block))
                parts.append(markdown)
                metadata.append({"element": index, "type": kind, "level": level})
                output_bytes += len(markdown.encode("utf-8"))
                if output_bytes > MAX_OUTPUT_BYTES:
                    raise ValueError("Word 提取正文过大，请拆分后重试。")
                continue
            else:
                stack = []
        output_bytes += len(markdown.encode("utf-8"))
        if output_bytes > MAX_OUTPUT_BYTES:
            raise ValueError("Word 提取正文过大，请拆分后重试。")
        blocks.append(block)
        parts.append(markdown)
        metadata.append({"element": index, "type": block["type"]})
    if not parts:
        raise ValueError("Word 文档未提取到正文，图片内容暂不识别。")
    return {"status": "parsed", "content": "\n\n".join(parts), "blocks": blocks, "metadata": metadata, "parser": "python-docx"}


if __name__ == "__main__":
    try:
        result = parse_word(sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1))
    except ValueError as cause:
        result = {"error": str(cause)}
    except Exception:
        result = {"error": "Word 解析失败，请检查文档是否损坏或加密。"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
