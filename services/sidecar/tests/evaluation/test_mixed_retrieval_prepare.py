"""混合检索只索引实际文件解析结果，不能把清单参考正文当作提取结果。"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.rag import prepare_retrieval as module
from src import config


def test_prepare_reads_file_and_indexes_parser_output_not_manifest_answer(tmp_path, monkeypatch):
    source = tmp_path / 'files'
    source.mkdir()
    body = b'%PDF-synthetic-input'
    (source / 'sample.pdf').write_bytes(body)
    manifest = {'documents': [{'id': 'sample', 'title': 'Sample', 'content': '不得混入索引的参考答案',
        'file_type': 'pdf', 'variant': 'pdf_scan', 'filename': 'sample.pdf',
        'file_sha256': hashlib.sha256(body).hexdigest(), 'expected_fragments': ['5200']}],
        'queries': [{'id': 'q1', 'question': '容量？', 'relevant_document_ids': ['sample']}]}
    (source / 'manifest.json').write_text(json.dumps(manifest))
    indexed = []
    async def parse(content, kind):
        assert content == body and kind == 'pdf'
        return {'content': '实际 OCR 结果 5200mAh', 'parser': 'pymupdf+baidu_ocr',
                'metadata': [{'page_number': 1, 'content': '实际 OCR 结果 5200mAh', 'extraction_method': 'baidu_ocr'}]}
    class Embeddings:
        async def aembed_documents(self, texts):
            indexed.extend(texts)
            return [[1.0] + [0.0] * 1023 for _ in texts]
        async def aembed_query(self, text):
            return [1.0] + [0.0] * 1023
    monkeypatch.setattr(module, 'parse_document', parse)
    monkeypatch.setattr(module, 'ArkEmbeddings', Embeddings)
    monkeypatch.setattr(config, 'DATA_ROOT', config.DATA_ROOT)
    monkeypatch.setattr(config, 'TEMP_DIR', config.TEMP_DIR)
    output = tmp_path / 'output'
    asyncio.run(module.prepare(output, source))
    prepared = json.loads((output / 'prepared.json').read_text())
    doc = prepared['documents'][0]
    assert doc['content'] == '实际 OCR 结果 5200mAh'
    assert doc['parse_audit']['ocr_pages'] == 1
    assert doc['parse_audit']['missing_fragments'] == []
    assert indexed and all('参考答案' not in value for value in indexed)
    (source / 'sample.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError, match='指纹'):
        asyncio.run(module.prepare(output, source))
