# -*- coding: utf-8 -*-
"""规则书检索（M2 RAG）：自实现字级 BM25 + 字段加权，可解释命中。

对外接口：
    from coc_keeper.retrieval import search_rules
    hits = search_rules("食尸鬼", top_k=5)          # 全库
    hits = search_rules("闪避", type="skill")       # 按类型过滤

    # 底层：注入自建 Index（避免重复加载）见 retrieval.search.search
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from .index import Index
from .search import RuleHit, search
from .tokenizer import tokenize

# 默认语料（gitignored 生成物）
_DEFAULT_CHUNKS = Path(__file__).resolve().parents[3] / "data" / "rulebook" / "rules_chunks.json"


@lru_cache(maxsize=1)
def _default_index() -> Index:
    """懒加载默认索引（进程内缓存）。"""
    if not _DEFAULT_CHUNKS.exists():
        raise FileNotFoundError(
            f"规则块语料不存在: {_DEFAULT_CHUNKS}\n"
            "请先运行 `python scripts/extract_rules.py --build` 生成。"
        )
    return Index.from_chunk_file(_DEFAULT_CHUNKS)


def search_rules(
    query: str,
    top_k: int = 5,
    type: Optional[str] = None,
    *,
    index: Optional[Index] = None,
) -> list[RuleHit]:
    """便捷检索入口（自动加载默认语料，可传入自定义 index）。"""
    idx = index if index is not None else _default_index()
    return search(idx, query, top_k=top_k, type=type)


__all__ = ["search_rules", "search", "Index", "RuleHit", "tokenize"]
