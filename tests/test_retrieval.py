# -*- coding: utf-8 -*-
from coc_keeper.rules.retrieval import RuleIndex, load_default_index, tokenize


def test_tokenize_mixed_language():
    assert tokenize("奖励骰 d100") == ["奖", "励", "骰", "d100"]


def test_bm25_search_returns_page_citation():
    index = RuleIndex.from_text(
        "===== 第 10 页 =====\n角色创建与职业。\n"
        "===== 第 70 页 =====\n奖励骰额外掷十位骰并取较小结果。"
    )
    hit = index.search("奖励骰怎么掷", limit=1)[0]
    assert hit.page == 70
    assert hit.score > 0


def test_empty_query_and_builtin_fallback(tmp_path):
    assert RuleIndex.from_text("文本").search("") == []
    assert RuleIndex.from_text("文本").search("完全无关") == []
    index = load_default_index(tmp_path / "missing.txt")
    assert index.search("临时性疯狂")[0].page == 133
