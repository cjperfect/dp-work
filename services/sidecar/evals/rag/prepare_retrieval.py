"""使用真实 Markdown Loader、父子分块和方舟 Embedding 准备隔离检索评测。"""
import asyncio
import argparse
import hashlib
import json
import sys
import re
import time
from pathlib import Path

from src import config
from src.knowledge.parsers.dispatcher import parse_document
from src.knowledge.rag.chunking import split_document
from src.knowledge.rag.embedding import ArkEmbeddings, profile
from .retrieval_corpus import build_corpus


async def prepare(output: Path, files: Path | None = None, request_interval: float = 0):
    """导出可核对的文档、标签和向量缓存，不读取用户知识库。"""
    output.mkdir(parents=True, exist_ok=True)
    corpus = json.loads((files / 'manifest.json').read_text()) if files else build_corpus()
    if files:
        for doc in corpus['documents']:
            source = files / doc['filename']
            if source.parent != files or hashlib.sha256(source.read_bytes()).hexdigest() != doc['file_sha256']:
                raise ValueError('源文件路径或指纹与清单不一致。')
    fingerprint = hashlib.sha256(json.dumps(corpus, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    root = Path(__file__).resolve().parents[2]
    pipeline_sha = hashlib.sha256(b''.join((root / path).read_bytes() for path in (
        'src/knowledge/parsers/pdf.py', 'src/knowledge/parsers/text.py', 'src/providers/ocr/baidu.py',
        'src/knowledge/rag/chunking.py'))).hexdigest()
    cache = output / 'prepared.json'
    if cache.exists():
        existing = json.loads(cache.read_text())
        if existing.get('fingerprint') == fingerprint and existing.get('profile') == profile() and existing.get('pipeline_sha') == pipeline_sha:
            print('复用相同语料及向量空间的缓存。', flush=True)
            return
    config.DATA_ROOT = output / 'runtime'
    config.TEMP_DIR = config.DATA_ROOT / 'temp'
    (output / 'documents').mkdir(exist_ok=True)
    (output / 'corpus.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=2))
    embedder = ArkEmbeddings()
    progress = output / 'vector-cache' / hashlib.sha256((fingerprint + profile() + pipeline_sha).encode()).hexdigest()
    progress.mkdir(parents=True, exist_ok=True)
    lock, last_request = asyncio.Lock(), 0.0
    requests = asyncio.Semaphore(4)
    async def embed_text(text, query=False):
        nonlocal last_request
        cached = progress / ('text-' + hashlib.sha256((str(query) + text).encode()).hexdigest() + '.json')
        if cached.exists():
            return json.loads(cached.read_text())
        async with requests:
            async with lock:
                await asyncio.sleep(max(0, last_request + request_interval - time.monotonic()))
                last_request = time.monotonic()
            result = await embedder.aembed_query(text) if query else (await embedder.aembed_documents([text]))[0]
            cached.write_text(json.dumps(result))
            return result

    for number, doc in enumerate(corpus['documents'], 1):
        saved = progress / (doc['id'] + '.json')
        if saved.exists():
            doc.update(json.loads(saved.read_text()))
            print(f'复用文档向量 {number}/{len(corpus["documents"])}', flush=True)
            continue
        if files:
            content = (files / doc['filename']).read_bytes()
        else:
            content = doc['content'].encode()
            doc.update(file_type='md', variant='md')
        parsed = await parse_document(content, doc['file_type'])
        normalize = lambda value: re.sub(r'\s+', '', value).lower()
        missing = [fact for fact in doc.get('expected_fragments', []) if normalize(fact) not in normalize(parsed['content'])]
        doc['parse_audit'] = {'parser': parsed['parser'], 'missing_fragments': missing,
            'expected_fragments': doc.get('expected_fragments', []),
            'ocr_pages': sum(page.get('extraction_method') == 'baidu_ocr' for page in parsed.get('metadata', []))}
        doc['content'] = parsed['content']
        doc['parse_metadata'] = parsed.get('metadata', [])
        (output / 'documents' / (doc['id'] + '.md')).write_text(parsed['content'])
        doc['parents'] = split_document(parsed['content'], parsed.get('metadata'))
        children = [child for parent in doc['parents'] for child in parent['children']]
        vectors = list(await asyncio.gather(*(embed_text(child['content']) for child in children))) if request_interval else await embedder.aembed_documents([child['content'] for child in children])
        for child, vector in zip(children, vectors, strict=True):
            child['embedding'] = vector
        saved.write_text(json.dumps(doc, ensure_ascii=False))
        audit = f'遗漏锚点 {len(missing)}' if doc.get('expected_fragments') else '未配置逐字锚点'
        print(f'解析及向量化 {number}/{len(corpus["documents"])}：{doc["id"]} [{doc["variant"]}]；{audit}', flush=True)
    semaphore = asyncio.Semaphore(4)
    async def query_vector(query):
        async with semaphore:
            saved = progress / ('query-' + hashlib.sha256(query['question'].encode()).hexdigest() + '.json')
            if saved.exists():
                query['embedding'] = json.loads(saved.read_text())
            else:
                query['embedding'] = await embed_text(query['question'], True) if request_interval else await embedder.aembed_query(query['question'])
                saved.write_text(json.dumps(query['embedding']))
    await asyncio.gather(*(query_vector(query) for query in corpus['queries']))
    cache.write_text(json.dumps({**corpus, 'fingerprint': fingerprint, 'pipeline_sha': pipeline_sha, 'profile': profile(),
                                'embedding_model': config.EMBEDDING_MODEL}, ensure_ascii=False))
    print(f'已准备 {len(corpus["documents"])} 篇文档、{len(corpus["queries"])} 个查询。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--files', type=Path)
    parser.add_argument('--request-interval', type=float, default=0)
    args = parser.parse_args()
    try:
        asyncio.run(prepare(args.output.resolve(), args.files.resolve() if args.files else None, max(0, args.request_interval)))
    except Exception as cause:
        print('向量准备失败：' + type(cause).__name__, file=sys.stderr)
        raise SystemExit(1)
