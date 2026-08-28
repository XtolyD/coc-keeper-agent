# -*- coding: utf-8 -*-
import pytest

from coc_keeper.retrieval.tokenizer import normalize, tokenize
from coc_keeper.retrieval.bm25 import idf, score_query
from coc_keeper.retrieval.index import Index
from coc_keeper.retrieval.search import search


def _chunk(type_, name, text, page=1, path=""):
    return {
        "type": type_, "name": name, "title": name, "text": text,
        "page": page, "start_page": page, "end_page": page,
        "path": path, "order": 0, "lines": text.splitlines(),
    }


# ---- tokenizer --------------------------------------------------------------
def test_tokenize_chinese_unigram():
    assert tokenize("奖励骰怎么投") == ["奖", "励", "骰", "怎", "么", "投"]


def test_tokenize_ascii_and_digits():
    # 连续 ascii/数字 合为一个 token，小写化；空格分隔不同词
    assert tokenize("1D100") == ["1d100"]
    assert tokenize("STR 90") == ["str", "90"]
    assert "5d6" in tokenize("（5D6×5）")


def test_tokenize_fullwidth_normalized():
    # 全角数字/字母 → 半角
    assert tokenize("１Ｄ６") == ["1d6"]
    assert "1d100" in tokenize("１Ｄ１００")


def test_tokenize_mixed():
    toks = tokenize("奖励骰怎么投 1D100")
    assert toks == ["奖", "励", "骰", "怎", "么", "投", "1d100"]


def test_normalize_removes_whitespace():
    # normalize 只做全角→半角 + 去首尾空白，保留词间空格（作为 token 分隔）
    assert normalize("奖 励 骰") == "奖 励 骰"
    assert normalize(" Ａ Ｂ ") == "A B"
    assert normalize("Ａ　Ｂ") == "A B"   # 全角空格 → 普通空格
    assert tokenize(" Ａ Ｂ ") == ["a", "b"]


# ---- bm25 -------------------------------------------------------------------
def test_idf_basic():
    assert idf(0, 10) == 0.0           # df=0 → 无区分度
    assert idf(1, 100) > 0             # 稀有词 → 高 idf
    assert idf(1, 100) > idf(10, 100)  # df 越小 idf 越大
    # 出现在绝大多数文档 → idf 很小但非严格 0（标准 BM25 行为）
    assert idf(99, 100) < 0.05


def test_score_query_matching_doc_scores_higher():
    doc_freq = {"奖": 5, "励": 5, "骰": 5, "怎": 5, "么": 5}
    q = ["奖", "励", "骰"]
    # 相关文档：三个词都出现
    doc_rel = ["奖", "励", "骰"] * 3
    # 不相关文档：都不出现
    doc_none = ["无", "关"]
    s_rel = score_query(q, doc_rel, doc_freq, 100, 3.0)
    s_none = score_query(q, doc_none, doc_freq, 100, 3.0)
    assert s_rel > 0
    assert s_none == 0.0


def test_score_query_doc_freq_penalty():
    # 高 df 的词（常见词）贡献更低
    doc_freq_common = {"食": 900, "尸": 900, "鬼": 900}
    doc_freq_rare = {"食": 5, "尸": 5, "鬼": 5}
    q = ["食", "尸", "鬼"]
    doc = ["食", "尸", "鬼"]
    s_common = score_query(q, doc, doc_freq_common, 1000, 3.0)
    s_rare = score_query(q, doc, doc_freq_rare, 1000, 3.0)
    assert s_rare > s_common


def test_score_query_long_doc_penalized():
    doc_freq = {"奖": 5, "励": 5, "骰": 5}
    q = ["奖", "励", "骰"]
    short = ["奖", "励", "骰"]
    long = ["奖", "励", "骰"] + ["无"] * 1000
    s_short = score_query(q, short, doc_freq, 100, 3.0)
    s_long = score_query(q, long, doc_freq, 100, 3.0)
    assert s_short > s_long


def test_score_query_empty():
    assert score_query([], ["奖"], {"奖": 1}, 10, 3.0) == 0.0
    assert score_query(["奖"], [], {"奖": 1}, 10, 3.0) == 0.0


# ---- index / search ---------------------------------------------------------
def _build_index(chunks):
    return Index.build(chunks)


def test_index_build_statistics():
    chunks = [
        _chunk("monster", "食尸鬼", "食尸鬼 是一种 怪物"),
        _chunk("skill", "闪避", "闪避 技能 用于 躲避"),
    ]
    idx = _build_index(chunks)
    assert idx.total_docs == 2
    assert "食" in idx.doc_freq
    assert "食" in idx.name_doc_freq
    assert idx.avg_doc_len > 0


def test_search_ranks_exact_name_match_first():
    chunks = [
        _chunk("monster", "食尸鬼", "食尸鬼 是 克苏鲁 神话 中的 怪物"),
        _chunk("monster", "妖鬼", "妖鬼 也会 吃 尸鬼 同类"),
        _chunk("rule", "怪物", "怪物 的 一般 规则"),
    ]
    idx = _build_index(chunks)
    hits = search(idx, "食尸鬼", top_k=3)
    assert hits[0].name == "食尸鬼"
    assert hits[0].type == "monster"
    assert hits[0].score > 0
    assert any(t in "食尸鬼" for t in hits[0].keywords)  # 命中关键词可解释
    assert "name" in hits[0].fields and "text" in hits[0].fields


def test_search_type_filter():
    chunks = [
        _chunk("monster", "食尸鬼", "食尸鬼 是 怪物"),
        _chunk("skill", "闪避", "闪避 是 技能"),
    ]
    idx = _build_index(chunks)
    # 用同时出现在两者的字去测，但 type 过滤应只返回 monster
    hits = search(idx, "食", top_k=5, type="monster")
    assert all(h.type == "monster" for h in hits)


def test_search_empty_query():
    idx = _build_index([_chunk("rule", "", "内容")])
    assert search(idx, "   ") == []


def test_search_returns_metadata():
    chunks = [
        _chunk("monster", "食尸鬼", "食尸鬼 描述", page=266, path="第十四章/14.1"),
    ]
    idx = _build_index(chunks)
    h = search(idx, "食尸鬼", top_k=1)[0]
    assert h.page == 266
    assert h.start_page == 266 and h.end_page == 266
    assert h.path == "第十四章/14.1"
    assert h.snippet  # 非空片段
