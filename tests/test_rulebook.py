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


# ---- 残块回合并：属性名不作为残块 ------------------------------------------
def test_merge_attr_name_not_merged():
    # 属性名（如 体质）是独立新标题，不应被并进前一特征值行尾。
    from coc_keeper.merge_fragments import merge_tail_fragments
    r = _rect()
    # 前一宽行 + 属性名 体质（gap≤6）
    blocks = [
        _block(324, 135.8, 560, 146, "200+：怪物之力"),
        _block(439.1, 165.9, 460, 178, "体质"),
    ]
    out = merge_tail_fragments(blocks, r)
    assert len(out) == 2            # 不应被合并
    assert out[0].text == "200+：怪物之力"
    assert out[1].text.strip() == "体质"


def test_merge_real_fragment_still_merged():
    # 真正的行尾残碎（如 移动８ 的断行）仍应合并。
    from coc_keeper.merge_fragments import merge_tail_fragments
    r = _rect()
    blocks = [
        _block(45.6, 490, 279, 504, "若敏捷或力量之一大于等于体型或三者相等：移"),
        _block(57.8, 507.6, 82, 518, "动８"),
    ]
    out = merge_tail_fragments(blocks, r)
    assert len(out) == 1
    assert out[0].text == "若敏捷或力量之一大于等于体型或三者相等：移动８"


def test_merge_attr_name_set_contains_all_8():
    from coc_keeper.merge_fragments import ATTR_NAMES
    assert ATTR_NAMES == {"力量", "体质", "体型", "敏捷", "外貌", "智力", "意志", "教育"}


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
