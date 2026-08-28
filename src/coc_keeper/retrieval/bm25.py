# -*- coding: utf-8 -*-
"""自实现 BM25 检索打分（零依赖）。

仅实现标准 BM25 的**打分部分**（纯函数）。idf / 文档词频 / 平均长度等统计
由 `index.py` 预计算传入，保持这里无状态、可单测。

参数（见 docs/retrieval-spec.md §4.3）：
    k1 = 1.5   词频饱和系数
    b  = 0.75   文档长度归一系数

公式（Robertson 变体，取常见 BM25 形式）：
    idf(t) = ln( (N - df + 0.5) / (df + 0.5) + 1 )
    score(q, d) = Σ_t  idf(t) * tf*(k1+1) / (tf + k1*(1 - b + b*len_d/avg_dl))
"""
from __future__ import annotations

import math

K1 = 1.5
B = 0.75


def idf(doc_freq: int, total_docs: int) -> float:
    """BM25 idf。df≤0 或 N≤0 时视为 0（无区分度）。"""
    if doc_freq <= 0 or total_docs <= 0:
        return 0.0
    return math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)


def score_query(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freq: dict[str, int],
    total_docs: int,
    avg_doc_len: float,
    *,
    k1: float = K1,
    b: float = B,
) -> float:
    """计算 query 对单个文档（块）的 BM25 得分。

    参数：
        query_tokens:   查询 token 列表
        doc_tokens:     该文档 token 列表
        doc_freq:       {token: 出现该 token 的文档数}（df）
        total_docs:     文档总数（N）
        avg_doc_len:    平均文档长度
        k1 / b:         BM25 超参

    返回：BM25 总分（≥0）。
    """
    if not query_tokens or not doc_tokens or total_docs <= 0 or avg_doc_len <= 0:
        return 0.0
    doc_len = len(doc_tokens)
    # 文档内词频
    tf: dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1

    total = 0.0
    # 只对 query 中出现的词计分（set 去重，每个词计一次）
    for qt in set(query_tokens):
        tf_q = tf.get(qt)
        if not tf_q:
            continue
        idf_q = idf(doc_freq.get(qt, 0), total_docs)
        if idf_q == 0.0:
            continue
        denom = tf_q + k1 * (1 - b + b * doc_len / avg_doc_len)
        total += idf_q * (tf_q * (k1 + 1) / denom)
    return total
