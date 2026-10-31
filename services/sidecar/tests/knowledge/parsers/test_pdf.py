"""验证真实 PDF 提取、表格、边界和RPC 方法分发。"""
import asyncio
import base64
from pathlib import Path
from unittest.mock import AsyncMock

import pymupdf
import pytest

from src import config
from src.knowledge.parsers.pdf import parse_pdf
from src.knowledge.parsers import dispatcher
from src.transport.handlers import dispatch, OperationError


def sample_pdf():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 40), "Project knowledge sample")
    for x in [50, 200, 350]:
        page.draw_line((x, 70), (x, 160))
    for y in [70, 100, 130, 160]:
        page.draw_line((50, y), (350, y))
    for y, row in [(90, ["Name", "Value"]), (120, ["Alpha", "42"]), (150, ["Beta", "99"])]:
        for x, text in zip([60, 210], row):
            page.insert_text((x, y), text)
    page = document.new_page()
    page.insert_text((50, 50), "Second page content")
    result = document.tobytes()
    document.close()
    return result


def test_pdf_text_tables_metadata_and_cleanup(tmp_path):
    result = parse_pdf(sample_pdf(), tmp_path)
    assert result["status"] == "parsed"
    assert "Project knowledge sample" in result["content"]
    assert "|" in result["content"] and "Alpha" in result["content"]
    assert "42" in result["content"]
    assert [page["page_number"] for page in result["metadata"]] == [1, 2]
    assert "Second page content" in result["metadata"][1]["content"]
    assert "source" not in str(result["metadata"])
    assert list(tmp_path.iterdir()) == []


def test_empty_scanned_invalid_encrypted_and_page_limit(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="有效 PDF"):
        parse_pdf(b"not pdf", tmp_path)
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(ValueError, match="未提取到文字"):
        parse_pdf(doc.tobytes(), tmp_path)
    encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    with pytest.raises(ValueError, match="加密"):
        parse_pdf(encrypted, tmp_path)
    from src.knowledge.parsers import pdf
    monkeypatch.setattr(pdf, "MAX_PAGES", 1)
    with pytest.raises(ValueError, match="200 页"):
        parse_pdf(sample_pdf(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_legacy_doc_is_unsupported():
    with pytest.raises(dispatcher.ParseError, match="旧版 DOC"):
        asyncio.run(dispatcher.parse_document(b"legacy", "doc"))


def test_process_parser_and_rpc_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    async def case():
        # 实际运行独立解析进程。
        result = await dispatcher.parse_pdf(sample_pdf())
        assert result["status"] == "parsed" and len(result["metadata"]) == 2
        response = await dispatch("knowledge.parse", {"content_base64": base64.b64encode(sample_pdf()).decode(), "file_type": "pdf"}, None)
        assert response["parser"] == "pymupdf"
        with pytest.raises(OperationError) as error:
            await dispatch("knowledge.parse", {"content_base64": base64.b64encode(b"not pdf").decode(), "file_type": "pdf"}, None)
        assert error.value.status == 400
    asyncio.run(case())


def test_timeout_kills_process(monkeypatch):
    class FakeProcess:
        returncode = None
        killed = False
        async def communicate(self, content):
            await asyncio.sleep(10)
        def kill(self):
            self.killed = True
        async def wait(self):
            self.returncode = -9
    process = FakeProcess()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    monkeypatch.setattr(config, "PDF_PARSE_TIMEOUT", .01)
    with pytest.raises(dispatcher.ParseError, match="超时"):
        asyncio.run(dispatcher.parse_pdf(b"%PDF-1.4"))
    assert process.killed


def scanned_pdf(mixed=False):
    """生成只含栅格文字的扫描页，避免依赖用户文档。"""
    source = pymupdf.open()
    source.new_page().insert_text((40, 60), "Battery capacity: 5200 mAh", fontsize=18)
    image = source[0].get_pixmap().tobytes("png")
    doc = pymupdf.open()
    if mixed:
        doc.new_page().insert_text((40, 60), "Native text page")
    page = doc.new_page()
    page.insert_image(page.rect, stream=image)
    doc.new_page()  # 真正的空白页不调用 OCR。
    content = doc.tobytes()
    source.close()
    doc.close()
    return content


def test_scanned_and_mixed_pages_use_ocr_and_preserve_page_numbers(tmp_path, monkeypatch):
    from src.knowledge.parsers import pdf
    calls = []
    def recognize(self, image):
        calls.append(image)
        assert image.startswith(b'\xff\xd8')
        return "Battery capacity: 5200 mAh"
    monkeypatch.setattr(pdf.BaiduOCR, 'recognize', recognize)
    result = parse_pdf(scanned_pdf(mixed=True), tmp_path)
    assert result['parser'] == 'pymupdf+baidu_ocr'
    assert result['content'].index('Native text page') < result['content'].index('5200')
    assert len(calls) == 1
    assert [page['page_number'] for page in result['metadata']] == [1, 2, 3]
    assert result['metadata'][1]['extraction_method'] == 'baidu_ocr'
    assert result['metadata'][2]['content'] == ''
    assert not list(tmp_path.iterdir())


def test_scanned_page_requires_credentials_without_returning_partial_text(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'BAIDU_OCR_API_KEY', '')
    monkeypatch.setattr(config, 'BAIDU_OCR_SECRET_KEY', '')
    with pytest.raises(ValueError, match='第 2 页.*BAIDU_OCR_API_KEY'):
        parse_pdf(scanned_pdf(mixed=True), tmp_path)
    assert not list(tmp_path.iterdir())


def test_ocr_limit_checked_before_request(tmp_path, monkeypatch):
    from src.knowledge.parsers import pdf
    monkeypatch.setattr(config, 'BAIDU_OCR_MAX_PAGES', 1)
    def forbidden(*args):
        pytest.fail('超出页数限制前不应调用 OCR')
    monkeypatch.setattr(pdf.BaiduOCR, 'recognize', forbidden)
    doc = pymupdf.open(stream=scanned_pdf(), filetype='pdf')
    doc.fullcopy_page(0)
    with pytest.raises(ValueError, match='最多识别 1'):
        parse_pdf(doc.tobytes(), tmp_path)
    doc.close()
    assert not list(tmp_path.iterdir())


def test_native_pdf_never_calls_ocr(tmp_path, monkeypatch):
    from src.knowledge.parsers import pdf
    def forbidden(*args):
        pytest.fail('文字型 PDF 不应调用 OCR')
    monkeypatch.setattr(pdf.BaiduOCR, 'recognize', forbidden)
    assert parse_pdf(sample_pdf(), tmp_path)['parser'] == 'pymupdf'


def test_ocr_failure_is_not_saved_as_partial_success(tmp_path, monkeypatch):
    from src.knowledge.parsers import pdf
    def failed(*args):
        raise ValueError('百度 OCR 调用额度已用尽')
    monkeypatch.setattr(pdf.BaiduOCR, 'recognize', failed)
    with pytest.raises(ValueError, match='第 2 页.*额度'):
        parse_pdf(scanned_pdf(mixed=True), tmp_path)
    assert not list(tmp_path.iterdir())
