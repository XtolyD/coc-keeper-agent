# -*- coding: utf-8 -*-
"""规则书检索：索引构建（从 rules_chunks.json 到可查询的 BM25 索引）。

设计（见 docs/retrieval-spec.md §4.6）：
- 由 `rules_chunks.json` 在**运行时**构建，不序列化倒排（862 块规模小）。
- 为每个块预计算 `name_tokens` / `text_tokens`，并统计全局 df / 平均文档长度。
- 提供 `Index.from_chunk_file(path)` 与 `Index.build(chunks)` 两种入口。

对外只暴露 `Index`（供 `search.py` 使用），不做查询逻辑。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .tokenizer import tokenize


@dataclass
class Index:
    """BM25 检索索引（内存态，懒构建）。"""
    chunks: list[dict] = field(default_factory=list)
    doc_freq: dict[str, int] = field(default_factory=dict)   # token -> df
    total_docs: int = 0
    avg_doc_len: float = 0.0          # 各块 text token 长度的平均值
    name_doc_freq: dict[str, int] = field(default_factory=dict)  # name 字段的 df

    # 每个块的预计算 token（按块 order 对齐）
    _name_tokens: list[list[str]] = field(default_factory=list)
    _text_tokens: list[list[str]] = field(default_factory=list)

    @classmethod
    def build(cls, chunks: list[dict]) -> "Index":
        """由块列表构建索引。"""
        idx = cls(chunks=list(chunks))
        idx.total_docs = len(chunks)

        doc_freq: dict[str, int] = {}
        name_df: dict[str, int] = {}
        text_len_sum = 0

        for c in chunks:
            name_toks = tokenize(c.get("name", ""))
            text_toks = tokenize(c.get("text", ""))
            idx._name_tokens.append(name_toks)
            idx._text_tokens.append(text_toks)
            text_len_sum += len(text_toks)

            for t in set(text_toks):
                doc_freq[t] = doc_freq.get(t, 0) + 1
            for t in set(name_toks):
                name_df[t] = name_df.get(t, 0) + 1

        idx.doc_freq = doc_freq
        idx.name_doc_freq = name_df
        idx.avg_doc_len = (text_len_sum / len(chunks)) if chunks else 0.0
        return idx

    @classmethod
    def from_chunk_file(cls, path: str | Path) -> "Index":
        """从 rules_chunks.json 构建索引。"""
        p = Path(path)
        chunks = json.loads(p.read_text(encoding="utf-8"))
        return cls.build(chunks)

    def __len__(self) -> int:
        return self.total_docs
