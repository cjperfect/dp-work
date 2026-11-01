"""检索语料标签完整且跨文档问题要求所有相关来源。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.rag.retrieval_corpus import build_corpus


def test_corpus_has_thirty_documents_and_seventy_valid_queries():
    corpus = build_corpus()
    assert len(corpus['documents']) == 30
    assert len(corpus['queries']) == 70
    ids = {doc['id'] for doc in corpus['documents']}
    assert len(ids) == 30
    assert len({query['id'] for query in corpus['queries']}) == 70
    for query in corpus['queries']:
        assert query['relevant_document_ids']
        assert set(query['relevant_document_ids']) <= ids
        assert len(query['relevant_document_ids']) == (2 if query['group'] == 'multi_document' else 1)
    assert corpus == build_corpus()
