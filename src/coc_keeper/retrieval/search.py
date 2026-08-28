# -*- coding: utf-8 -*-
"""规则书检索：查询接口（search_rules）。

设计（见 docs/retrieval-spec.md §4.4/§4.5）：
- 字段加权：`name`（实体名，强字段） + `text`（正文）。
- 可解释：命中返回 `keywords`（query 实际命中的词）与 `fields`（各字段得分）。
- 类型过滤：`type="monster"` 等，仅在该类型内检索。
- 零状态、纯查询：`Index` 由调用方构建好传入（`search_rules` 的底层 `search`）。

对外接口：
    from coc_keeper.retrieval import search_rules   # 便捷入口（自动加载默认语料）
    from coc_keeper.retrieval.search import search  # 底层（传入 Index）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .bm25 import score_query
from .index import Index
from .tokenizer import tokenize

# 字段权重（可配置）
DEFAULT_W_NAME = 2.0         # name 字段权重（强字段）
DEFAULT_W_TEXT = 1.0         # text 字段权重
DEFAULT_NAME_EXACT_BONUS = 1.0  # query 完整命中 name 时的加成


@dataclass
class RuleHit:
    """一次规则命中（可解释）。"""
    type: str
    name: str
    page: int
    start_page: int
    end_page: int
    path: str
    snippet: str
    score: float
    keywords: list[str]
    fields: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "type": self.type, "name": self.name,
            "page": self.page, "start_page": self.start_page, "end_page": self.end_page,
            "path": self.path, "snippet": self.snippet,
            "score": round(self.score, 4), "keywords": self.keywords, "fields": self.fields,
        }


def _snippet(chunk: dict, query_tokens: list[str], width: int = 120) -> str:
    """从块中抽取命中上下文片段（优先命中行）。"""
    lines = chunk.get("lines") or [chunk.get("text", "")]
    for ln in lines:
        if any(t in ln for t in query_tokens):
            return ln[:width]
    return (chunk.get("text") or "")[:width]


def search(
    index: Index,
    query: str,
    top_k: int = 5,
    type: Optional[str] = None,
    *,
    w_name: float = DEFAULT_W_NAME,
    w_text: float = DEFAULT_W_TEXT,
    name_exact_bonus: float = DEFAULT_NAME_EXACT_BONUS,
) -> list[RuleHit]:
    """在索引中检索 query，返回按得分降序的 top_k 命中。

    参数：
        index:  已构建的 Index
        query:  查询文本
        top_k:  返回条数
        type:   仅在该实体类型内检索（如 "monster"），None 则全库。
        w_name / w_text / name_exact_bonus: 字段权重与精确命中加成。
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return []

    hits: list[RuleHit] = []
    for i, chunk in enumerate(index.chunks):
        if type is not None and chunk.get("type") != type:
            continue
        name_toks = index._name_tokens[i]
        text_toks = index._text_tokens[i]

        # 分字段 BM25（text 用全库 df；name 用其独立 df 统计）
        s_name = score_query(q_tokens, name_toks, index.name_doc_freq, index.total_docs, index.avg_doc_len)
        s_text = score_query(q_tokens, text_toks, index.doc_freq, index.total_docs, index.avg_doc_len)

        score = w_name * s_name + w_text * s_text
        # 实体名完整命中：加成
        name_str = chunk.get("name", "")
        if name_str and all(t in name_str for t in q_tokens):
            score += name_exact_bonus

        if score <= 0:
            continue

        # 命中的关键词 = query 中在 text 或 name 出现过的词
        keywords = [t for t in q_tokens if t in set(name_toks) or t in set(text_toks)]
        hits.append(RuleHit(
            type=chunk.get("type", "rule"),
            name=chunk.get("name", ""),
            page=chunk.get("page", 0),
            start_page=chunk.get("start_page", chunk.get("page", 0)),
            end_page=chunk.get("end_page", chunk.get("page", 0)),
            path=chunk.get("path", ""),
            snippet=_snippet(chunk, q_tokens),
            score=score,
            keywords=keywords,
            fields={"name": round(s_name, 4), "text": round(s_text, 4)},
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
