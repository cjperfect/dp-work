"""在随机临时 PG 数据库与 ES 索引中运行真实检索评测，完成后清理。"""
import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core import config
from src.infrastructure.database import session
from src.infrastructure.database.base import Base
from src.modules.users.models import User
from src.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from src.modules.knowledge.rag_models import KnowledgeParentChunk, KnowledgeChildChunk
from src.modules.knowledge.search_models import KnowledgeSearchSync
from src.modules.knowledge.search_client import SearchClient
from src.modules.knowledge.search_index import snapshot
from src.modules.knowledge import hybrid
from .retrieval_metrics import score, summarize

REPO = Path(__file__).resolve().parents[3]
TABLES = [User.__table__, KnowledgeBase.__table__, KnowledgeDocument.__table__,
          KnowledgeParentChunk.__table__, KnowledgeChildChunk.__table__, KnowledgeSearchSync.__table__]


async def seed(data, client, generation):
    """写入与线上相同的文档、父子块和向量模型，不经过用户账号或 MQ。"""
    async with session.transaction() as db:
        user = User(username='synthetic-eval', password_hash='not-a-login-hash', department='evaluation')
        db.add(user)
        await db.flush()
        base = KnowledgeBase(owner_id=user.id, name=f'{len(data["documents"])} 篇检索评测', description='独立临时数据库')
        db.add(base)
        await db.flush()
        for doc in data['documents']:
            task = str(uuid4())
            db.add(KnowledgeDocument(id=doc['id'], knowledge_base_id=base.id, title=doc['title'],
                content=doc['content'], file_type=doc.get('file_type', 'md'), parse_status='parsed',
                parse_content=doc['content'], parse_metadata=doc.get('parse_metadata'),
                parsed_at=datetime.now(timezone.utc), vector_status='indexed', vector_profile=data['profile'],
                vector_task_id=task, vectorized_at=datetime.now(timezone.utc)))
            await db.flush()
            for number, parent in enumerate(doc['parents']):
                parent_id = str(uuid4())
                db.add(KnowledgeParentChunk(id=parent_id, document_id=doc['id'], task_id=task, position=number,
                    content=parent['content'], chunk_metadata=parent['metadata']))
                await db.flush()
                for position, child in enumerate(parent['children']):
                    db.add(KnowledgeChildChunk(id=str(uuid4()), parent_id=parent_id, position=position,
                        content=child['content'], start_offset=child['start'], embedding=child['embedding']))
            db.add(KnowledgeSearchSync(document_id=doc['id'], revision=1, synced_revision=1,
                desired_task_id=task, index_generation=generation))
    for doc in data['documents']:
        await client.replace_document(doc['id'], await snapshot(doc['id']))
    return user.id, base.id


async def evaluate(path, modes=('vector', 'keyword', 'hybrid')):
    """对比三种召回方式；禁止将服务降级结果当作混合检索成绩。"""
    data = json.loads((path / 'prepared.json').read_text())
    documents, queries = data['documents'], data['queries']
    ids = {row['id'] for row in documents}
    if not documents or not queries or len(ids) != len(documents) or not (
        data.get('synthetic') or data.get('origin') == 'official-python-docs'):
        raise ValueError('需要受控文档及标注问题，文档 ID 不可重复。')
    if any(not row['relevant_document_ids'] or not set(row['relevant_document_ids']) <= ids for row in queries):
        raise ValueError('相关文档标签不能为空或指向语料外文档。')
    run_id = uuid4().hex
    database_name = 'dp_work_eval_' + run_id
    config.ELASTICSEARCH_INDEX = 'dp-work-eval-' + run_id
    original_url = session.async_database_url(config.DATABASE_URL)
    admin = create_async_engine(original_url, isolation_level='AUTOCOMMIT', hide_parameters=True)
    client = SearchClient()
    created_database = created_index = False
    results = []
    variants = {doc['id']: doc.get('variant', 'md') for doc in data['documents']}
    started = time.monotonic()
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
        created_database = True
        config.DATABASE_URL = original_url.set(database=database_name).render_as_string(hide_password=False)
        await session.init_db()
        async with session._engine.begin() as conn:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=TABLES))
        # 全新随机索引；从不删除或写入应用索引。
        created_index = True
        generation = await client.ensure_index()
        owner, base = await seed(data, client, generation)
        for mode in modes:
            config.ELASTICSEARCH_ENABLED = mode != 'vector'
            for query in data['queries']:
                before = time.monotonic()
                answer = await hybrid.search(owner, [base], query['question'],
                    query['embedding'] if mode != 'keyword' else None, data['profile'], 5)
                elapsed = (time.monotonic() - before) * 1000
                if answer['retrieval']['mode'] != mode or answer['retrieval']['keyword_pending']:
                    raise ValueError('检索服务降级或索引未就绪，不能输出完整评测成绩。')
                retrieved = list(dict.fromkeys(row['document_id'] for row in answer['sources']))
                results.append({'id': query['id'], 'group': query['group'], 'mode': mode,
                    'format_group': next(iter({variants[key] for key in query['relevant_document_ids']}))
                        if len({variants[key] for key in query['relevant_document_ids']}) == 1 else 'cross_format',
                    'question': query['question'], 'relevant_document_ids': query['relevant_document_ids'],
                    'retrieved_document_ids': retrieved, 'parent_ids': [row['parent_id'] for row in answer['sources']],
                    'latency_ms': elapsed, 'scores': score(query['relevant_document_ids'], retrieved)})
            print(mode + ': ' + json.dumps(summarize([row for row in results if row['mode'] == mode])), flush=True)
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
        report = {'created_at': datetime.now(timezone.utc).isoformat(), 'synthetic': data.get('synthetic', True),
            'origin': data.get('origin', 'synthetic'),
            'query_origin': data.get('query_origin', 'developer-labeled'), 'limitations': data.get('limitations', ''),
            'documents': len(data['documents']), 'queries': len(data['queries']), 'k': 5,
            'scope': '文档级指标；真实解析结果进入检索，实际返回前5个父块后按文档去重；不评价最终回答、图关系理解、上传或 MQ',
            'file_set': data.get('file_set', 'markdown-only'), 'pipeline_sha': data.get('pipeline_sha'),
            'file_counts': dict(Counter(variants.values())),
            'parse_audit': [{'document_id': doc['id'], 'variant': variants[doc['id']],
                            **doc.get('parse_audit', {})} for doc in data['documents']],
            'embedding_model': data['embedding_model'], 'profile': data['profile'], 'reranker': None,
            'corpus_fingerprint': data['fingerprint'], 'git_revision': revision,
            'retrieval_code_sha': hashlib.sha256(Path(hybrid.__file__).read_bytes()).hexdigest(),
            'rrf_constant': config.RAG_RRF_CONSTANT, 'candidates': config.RAG_HYBRID_CANDIDATES,
            'retrieval_total_seconds': time.monotonic() - started,
            'summary': {mode: summarize([row for row in results if row['mode'] == mode]) for mode in modes},
            'groups': {mode: {group: summarize([row for row in results if row['mode'] == mode and row['group'] == group])
                for group in sorted({row['group'] for row in results})} for mode in modes},
            'formats': {mode: {variant: summarize([row for row in results if row['mode'] == mode and row['format_group'] == variant])
                for variant in sorted({row['format_group'] for row in results})} for mode in modes},
            'results': results}
        output = path / ('report-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('报告：' + str(output), flush=True)
    finally:
        await session.close_db()
        try:
            if created_index:
                async with client.connection() as es:
                    await es.options(ignore_status=404).indices.delete(index=client.index)
        finally:
            try:
                if created_database:
                    async with admin.connect() as conn:
                        await conn.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
            finally:
                await admin.dispose()
        print('已清理临时 PG 数据库和 ES 索引。', flush=True)


def main():
    """先准备真实向量，再运行临时数据库检索；缓存避免重复模型调用。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO / '.dp-work/evals/rag/retrieval-30')
    parser.add_argument('--modes', nargs='+', choices=['vector', 'keyword', 'hybrid'], default=['vector', 'keyword', 'hybrid'])
    parser.add_argument('--request-interval', type=float, default=0)
    parser.add_argument('--prepared', action='store_true', help='已有向量缓存时跳过准备')
    parser.add_argument('--files', type=Path, help='混合 PDF/MD 文件所在目录，需有 manifest.json')
    args = parser.parse_args()
    path = args.output.resolve()
    if not args.prepared:
        sidecar = REPO / 'services/sidecar'
        python = sidecar / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')
        command = [str(python), '-u', '-m', 'evals.rag.prepare_retrieval', str(path)]
        command += ['--request-interval', str(max(0, args.request_interval))]
        if args.files:
            command += ['--files', str(args.files.resolve())]
        subprocess.run(command, cwd=sidecar, check=True)
    asyncio.run(evaluate(path, tuple(dict.fromkeys(args.modes))))


if __name__ == '__main__':
    main()
