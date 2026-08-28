# -*- coding: utf-8 -*-
import types

from coc_keeper.rulebook import (
    Block,
    build_structure,
    classify_columns,
    order_lines,
    _is_noise,
)


def _rect(w=612, h=792):
    return types.SimpleNamespace(width=w, height=h)


def _block(x0, y0, x1, y1, text):
    return Block(x0, y0, x1, y1, text)


# ---- 列分类 / 阅读顺序 ------------------------------------------------------
def test_classify_columns_splits_by_x_center():
    r = _rect()
    left = [_block(36, 50, 280, 60, "左一"), _block(36, 70, 280, 80, "左二")]
    right = [_block(324, 50, 560, 60, "右一"), _block(324, 70, 560, 80, "右二")]
    L, R, W = classify_columns(left + right, r)
    assert [b.text for b in L] == ["左一", "左二"]
    assert [b.text for b in R] == ["右一", "右二"]
    assert W == []


def test_classify_columns_marks_wide_block_separately():
    r = _rect()
    wide = [_block(30, 50, 580, 60, "跨栏标题")]  # 宽 > 58%
    L, R, W = classify_columns(wide, r)
    assert W == [wide[0]]
    assert L == [] and R == []


def test_order_lines_two_column_reads_left_then_right():
    r = _rect()
    blocks = [
        _block(324, 70, 560, 80, "右B"),
        _block(36, 50, 280, 60, "左A"),
        _block(36, 70, 280, 80, "左B"),
        _block(324, 50, 560, 60, "右A"),
    ]
    lines = order_lines(blocks, r)
    assert lines == ["左A", "左B", "右A", "右B"]


def test_order_lines_single_column_sorts_by_y():
    r = _rect()
    blocks = [
        _block(36, 90, 280, 100, "下文"),
        _block(36, 50, 280, 60, "上文"),
    ]
    assert order_lines(blocks, r) == ["上文", "下文"]


# ---- 噪声识别 ---------------------------------------------------------------
def test_is_noise_drops_header_and_footer_bands():
    r = _rect()
    assert _is_noise(_block(36, 740, 280, 762, "78"), r)      # 页码带
    assert _is_noise(_block(254, 30, 385, 45, "Call of"), r)  # 页眉带
    assert not _is_noise(_block(36, 60, 280, 70, "正文"), r)


def test_is_noise_drops_translator_and_citation_lines():
    r = _rect()
    assert _is_noise(_block(36, 60, 280, 70, "译/月夜白雨"), r)
    # 引文署名：含作品名《》或引号
    assert _is_noise(_block(36, 60, 280, 70, "——H.P.洛夫克拉夫特，《星之彩》"), r)
    assert _is_noise(_block(36, 60, 280, 70, "——亚瑟·马钦，《白人》"), r)
    assert _is_noise(_block(36, 60, 280, 70, "——H•P•洛夫克拉夫特，“门口之物”译者：竹子"), r)
    assert not _is_noise(_block(36, 60, 280, 70, "在ＣＯＣ中，每位玩家都需要"), r)


def test_is_noise_keeps_body_sentence_starting_with_em_dash():
    # 正文句子以破折号开头（转折/补充），必须保留，不能被误判为引文署名。
    r = _rect()
    assert not _is_noise(_block(36, 60, 280, 70, "——一团团不定型的黏性黑泥"), r)
    assert not _is_noise(_block(36, 60, 280, 70, "——他知道这是一个恐怖游戏"), r)
    assert not _is_noise(_block(36, 60, 280, 70, "——特别是克苏鲁和死灵之书"), r)


# ---- TOC 分层 ---------------------------------------------------------------
class _FakeDoc:
    def __init__(self, toc):
        self._toc = toc

    def get_toc(self):
        return self._toc


def test_build_structure_computes_page_ranges():
    toc = [
        [1, "第一章 介绍", 9],
        [2, "1.1 游戏概览", 9],
        [2, "1.2 合作与竞争", 10],
        [3, "1.2.1 赢家与输家", 10],
        [1, "第二章 爱手艺与克苏鲁神话", 16],
    ]
    root = build_structure(_FakeDoc(toc))
    assert len(root) == 2
    ch1, ch2 = root
    assert ch1.title == "第一章 介绍" and ch1.page_range == (9, 15)
    assert ch2.page_range == (16, 16)
    # 1.1 结束页 = 下一个同级 1.2 起点-1 = 9
    assert ch1.children[0].page_range == (9, 9)
    # 1.2 结束页 = 1.2.1 起点-1（同级迭代仍在 1.2 内，取 children 末尾边界前）不能越界
    assert ch1.children[1].title == "1.2 合作与竞争"
