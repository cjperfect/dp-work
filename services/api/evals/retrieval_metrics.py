"""按文档去重的检索指标；多来源问题以全部标注来源计算召回。"""
import math
import statistics


def score(relevant, retrieved, k=5):
    """计算 Recall、MRR、nDCG 和 Precision，不用任意命中率代替召回率。"""
    relevant = set(relevant)
    if not relevant or k < 1:
        raise ValueError('必须提供非空相关文档标签与正整数 k。')
    ranked = list(dict.fromkeys(retrieved))[:k]
    positions = [rank for rank, key in enumerate(ranked, 1) if key in relevant]
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), k) + 1))
    return {'recall@5': len(positions) / len(relevant),
            'mrr@5': 1 / positions[0] if positions else 0.0,
            'ndcg@5': sum(1 / math.log2(rank + 1) for rank in positions) / ideal,
            'precision@5': len(positions) / k,
            'hit@5': float(bool(positions))}


def summarize(rows):
    """宏平均质量指标及纯检索耗时，向量准备时间另行记录。"""
    if not rows:
        raise ValueError('评测结果不能为空。')
    latencies = sorted(row['latency_ms'] for row in rows)
    return {'queries': len(rows), **{key: statistics.mean(row['scores'][key] for row in rows)
        for key in ('recall@5', 'mrr@5', 'ndcg@5', 'precision@5', 'hit@5')},
        'retrieval_p50_ms': latencies[math.ceil(len(rows) * .5) - 1],
        'retrieval_p95_ms': latencies[math.ceil(len(rows) * .95) - 1]}
