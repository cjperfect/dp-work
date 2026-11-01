"""检索评测分母、排序及重复文档不会虚增指标。"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.retrieval_metrics import score, summarize


def test_multi_document_recall_is_not_any_hit():
    result = score(['a', 'b'], ['x', 'a', 'z'])
    assert result['recall@5'] == .5
    assert result['mrr@5'] == .5
    assert result['hit@5'] == 1
    assert result['precision@5'] == .2
    assert result['ndcg@5'] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))


def test_duplicates_missing_and_outside_cutoff():
    assert score(['a'], ['a', 'a', 'a'])['recall@5'] == 1
    assert score(['a'], ['a', 'a', 'a'])['precision@5'] == .2
    result = score(['a'], ['v', 'w', 'x', 'y', 'z', 'a'])
    assert all(value == 0 for value in result.values())
    assert score(['a'], [])['mrr@5'] == 0
    with pytest.raises(ValueError):
        score([], ['a'])


def test_summary_is_macro_average():
    rows = [{'latency_ms': 10, 'scores': score(['a'], ['a'])},
            {'latency_ms': 20, 'scores': score(['a', 'b'], ['b'])}]
    result = summarize(rows)
    assert result['recall@5'] == .75
    assert result['mrr@5'] == 1
    assert result['retrieval_p95_ms'] == 20
