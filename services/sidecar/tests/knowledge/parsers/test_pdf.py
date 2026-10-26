"""验证真实 PDF 提取、表格、边界和内部接口认证。"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from src import config
from src.knowledge.parsers.pdf import parse_pdf
from src.knowledge.parsers import dispatcher
from src.main import app


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


def test_process_parser_and_internal_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "test-internal")
    async def case():
        # 实际运行独立解析进程。
        result = await dispatcher.parse_pdf(sample_pdf())
        assert result["status"] == "parsed" and len(result["metadata"]) == 2
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://sidecar") as client:
            assert (await client.post("/internal/knowledge/parse", content=sample_pdf())).status_code == 401
            response = await client.post("/internal/knowledge/parse", headers={"X-Internal-Token": "test-internal"}, content=sample_pdf())
            assert response.status_code == 200, response.text
            assert response.json()["parser"] == "pymupdf"
            invalid = await client.post("/internal/knowledge/parse", headers={"X-Internal-Token": "test-internal"}, content=b"not pdf")
            assert invalid.status_code == 400
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
