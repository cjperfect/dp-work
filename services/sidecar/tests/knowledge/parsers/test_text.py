"""验证 LangChain 文本解析、格式保留和内部接口分发。"""
import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from src import config
from src.main import app
from src.knowledge.parsers import dispatcher
from src.knowledge.parsers import text as text_parser


def test_markdown_retains_structure_and_indentation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    markdown = "    indented code\r\n\r\n# 标题\r\n\r\n- 列表\r\n\r\n```python\r\nprint('hello')\r\n```\r\n\r\n| 名称 | 值 |\r\n|---|---|\r\n| A | 42 |\r\n"
    result = dispatcher.parse_markdown(b"\xef\xbb\xbf" + markdown.encode())
    assert result["content"] == markdown.replace("\r\n", "\n").strip("\n")
    assert result["parser"] == "langchain-text"
    assert result["metadata"] == [{"format": "md"}]
    assert list((tmp_path / "parsing").iterdir()) == []


def test_txt_keeps_markdown_like_characters_as_plain_text(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    source = "# 普通文字\n**不是加粗**\n\t缩进\x00"
    result = dispatcher.parse_txt(source.encode())
    assert result["content"] == source.replace("\x00", "")
    assert result["blocks"][0]["content"][0]["text"] == result["content"]
    assert list((tmp_path / "parsing").iterdir()) == []


def test_empty_invalid_encoding_and_limits(tmp_path, monkeypatch):
    for content, message in [(b"  \n\t", "正文为空"), (b"\xff\xfeinvalid", "UTF-8")]:
        with pytest.raises(ValueError, match=message):
            text_parser.load_text(content, "txt", tmp_path)
    monkeypatch.setattr(text_parser, "MAX_SOURCE_BYTES", 2)
    with pytest.raises(ValueError, match="20 MB"):
        text_parser.load_text(b"abc", "txt", tmp_path)
    monkeypatch.setattr(text_parser, "MAX_SOURCE_BYTES", 100)
    monkeypatch.setattr(text_parser, "MAX_OUTPUT_BYTES", 2)
    with pytest.raises(ValueError, match="正文过大"):
        text_parser.load_text(b"abc", "md", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_internal_endpoint_routes_text_and_preserves_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "test-internal")
    async def case():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://sidecar") as client:
            for kind in ("txt", "md"):
                path = "/internal/knowledge/parse?file_type=" + kind
                assert (await client.post(path, content=b"text")).status_code == 401
                response = await client.post(path, headers={"X-Internal-Token": "test-internal"}, content="# 中文正文".encode())
                assert response.status_code == 200, response.text
                assert response.json()["content"] == "# 中文正文"
                assert response.json()["metadata"][0]["format"] == kind
            invalid = await client.post("/internal/knowledge/parse?file_type=txt", headers={"X-Internal-Token": "test-internal"}, content=b"\xff")
            assert invalid.status_code == 422
            assert "UTF-8" in invalid.json()["detail"]["message"]
    asyncio.run(case())
