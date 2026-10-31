"""PyMuPDFLoader 提取正文及表格，无文字层页面使用百度 OCR。"""
import contextlib
import io
import json
import re
import sys
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from ... import config
from ...providers.ocr.baidu import BaiduOCR, MAX_FORM_BYTES, image_form

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PAGES = 200


def render_ocr_page(page) -> bytes:
    """渲染扫描页，限制像素及编码后的请求体大小。"""
    import pymupdf
    width, height = page.rect.width, page.rect.height
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise ValueError("PDF 页面尺寸无效。")
    scale = min(200 / 72, 4096 / max(width, height))
    for _ in range(8):
        if min(width, height) * scale < 64:
            raise ValueError("PDF 页面过窄或图像过大，无法安全进行 OCR，请调整后重试。")
        pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
        image = pixels.tobytes("jpeg", jpg_quality=90)
        if len(image_form(image)) <= MAX_FORM_BYTES:
            return image
        scale *= .8
    raise ValueError("PDF 页面图像过大，请拆分或降低分辨率后重试。")


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
        ocr_count = 0
        with pymupdf.open(source.name) as document:
            # 空白页不请求 OCR；混合 PDF 中的扫描页也必须识别，不能静默遗漏。
            scanned = [page for page in pages if not page["content"] and
                       (document[page["page"]].get_image_info() or document[page["page"]].get_drawings())]
            if len(scanned) > config.BAIDU_OCR_MAX_PAGES:
                raise ValueError(f"单个 PDF 最多识别 {config.BAIDU_OCR_MAX_PAGES} 个 OCR 页面，请拆分文件。")
            if scanned:
                with httpx.Client(timeout=config.BAIDU_OCR_TIMEOUT_SECONDS) as client:
                    ocr = BaiduOCR(client)
                    for page in scanned:
                        try:
                            recognized = ocr.recognize(render_ocr_page(document[page["page"]]))
                        except ValueError as cause:
                            raise ValueError(f"第 {page['page_number']} 页：{cause}") from None
                        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", recognized).replace("\r\n", "\n").strip()
                        output_size += len(text.encode("utf-8"))
                        if output_size > MAX_OUTPUT_BYTES:
                            raise ValueError("PDF 提取内容过大，请拆分文档后重试。")
                        page.update(content=text, extraction_method="baidu_ocr")
                        ocr_count += 1
        text = "\n\n---\n\n".join(page["content"] for page in pages if page["content"])
        if not text:
            raise ValueError("PDF 未提取到文字，请确认文件包含可识别的内容。")
        return {"status": "parsed", "content": text, "metadata": pages,
                "parser": "pymupdf+baidu_ocr" if ocr_count else "pymupdf"}


if __name__ == "__main__":
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = parse_pdf(sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1), Path(sys.argv[1]))
    except ValueError as cause:
        result = {"error": str(cause)}
    except Exception:
        result = {"error": "PDF 解析失败，请检查文件是否损坏，或重试。"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
