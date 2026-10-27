"""验证 LangChain 文本解析、格式保留和内部接口分发。"""
import asyncio
import base64
import pytest

from src import config
from src.transport.handlers import dispatch, OperationError
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


def test_rpc_routes_text_and_reports_invalid_encoding(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path)
    async def case():
        for kind in ("txt", "md"):
            response = await dispatch("knowledge.parse", {"file_type": kind, "content_base64": base64.b64encode("# 中文正文".encode()).decode()}, None)
            assert response["content"] == "# 中文正文"
            assert response["metadata"][0]["format"] == kind
        with pytest.raises(OperationError) as error:
            await dispatch("knowledge.parse", {"file_type": "txt", "content_base64": base64.b64encode(b"\xff").decode()}, None)
        assert error.value.status == 422 and "UTF-8" in error.value.detail["message"]
    asyncio.run(case())
