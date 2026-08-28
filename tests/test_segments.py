# -*- coding: utf-8 -*-
import pytest

from coc_keeper.docparser.result import Block
from coc_keeper.segments import (
    Chunk, chunk_content_list, is_noise, is_title, rulebook_type_fn,
)


def B(type="text", text="", text_level="", page_idx=0, bbox=None):
    return Block(type=type, text=text, text_level=text_level, page_idx=page_idx, bbox=bbox or [])


# ---- 噪声判定 ---------------------------------------------------------------
def test_is_noise():
    assert is_noise(B("header", "页眉"))
    assert is_noise(B("page_footnote", "脚注"))
    assert is_noise(B("page_number", "12"))
    assert not is_noise(B("text", "正文"))


def test_is_title():
    assert is_title(B("text", "第三章", text_level="1"))
    assert is_title(B("text", "3.1 第一步", text_level="2"))
    assert not is_title(B("text", "正文内容", text_level=""))
    assert not is_title(B("image"))


# ---- 分块：标题边界 + 正文累积 ----------------------------------------------
def test_chunk_title_and_body():
    blocks = [
        B("text", "第三章 创建调查员", text_level="1", page_idx=1),
        B("text", "正文第一段内容", text_level="", page_idx=1),
        B("text", "正文第二段内容", text_level="", page_idx=1),
        B("text", "3.1 第一步：决定属性", text_level="2", page_idx=2),
        B("text", "属性正文内容", text_level="", page_idx=2),
    ]
    chunks = chunk_content_list(blocks)
    # 章节引导正文归「第三章」块；3.1 的正文归「3.1」块
    assert len(chunks) == 2
    assert chunks[0].name == "第三章 创建调查员"
    assert chunks[0].path == "第三章 创建调查员"
    assert chunks[0].text == "第三章 创建调查员\n正文第一段内容\n正文第二段内容"
    assert chunks[1].name == "3.1 第一步：决定属性"
    assert chunks[1].path == "第三章 创建调查员/3.1 第一步：决定属性"
    assert chunks[1].text == "3.1 第一步：决定属性\n属性正文内容"


def test_chunk_noise_skipped():
    blocks = [
        B("header", "页眉", page_idx=0),
        B("text", "标题", text_level="1", page_idx=0),
        B("text", "正文", text_level="", page_idx=0),
        B("page_number", "7", page_idx=0),
        B("page_footnote", "脚注", page_idx=0),
    ]
    chunks = chunk_content_list(blocks)
    assert len(chunks) == 1
    assert chunks[0].name == "标题"
    assert chunks[0].text == "标题\n正文"


# ---- 特殊块：table / image 独立 --------------------------------------------
def test_chunk_table_and_image_standalone():
    blocks = [
        B("text", "第一章", text_level="1", page_idx=0),
        B("table", "表Ⅰ：伤害加值表", text_level="", page_idx=3),
        B("image", "", text_level="", page_idx=5),
        B("text", "正文", text_level="", page_idx=5),
    ]
    chunks = chunk_content_list(blocks)
    types = [c.type for c in chunks]
    assert "table" in types and "image" in types
    # table 块独立、image 块独立，正文回落到第一章块
    tbl = next(c for c in chunks if c.type == "table")
    assert tbl.page == 4  # page_idx=3 → 页码 4
    img = next(c for c in chunks if c.type == "image")
    assert img.page == 6


# ---- 跨页：正文累积，start/end 页正确 --------------------------------------
def test_chunk_cross_page_text():
    blocks = [
        B("text", "某规则", text_level="2", page_idx=0),
        B("text", "第一行内容", text_level="", page_idx=0),
        B("text", "第二行内容", text_level="", page_idx=1),  # 跨页
    ]
    chunks = chunk_content_list(blocks)
    body = chunks[-1]
    assert body.start_page == 1 and body.end_page == 2
    assert body.text == "某规则\n第一行内容\n第二行内容"


# ---- 类型判定：可注入 type_fn / rulebook_type_fn ---------------------------
def test_rulebook_type_fn_by_keyword():
    assert rulebook_type_fn("第四章 技能/4.4 技能列表", "") == "skill"
    assert rulebook_type_fn("第十四章 怪物/14.1", "") == "monster"
    assert rulebook_type_fn("第十二章 法术", "") == "spell"
    assert rulebook_type_fn("第六章 战斗", "") == "combat"
    assert rulebook_type_fn("第三章 属性", "") == "rule"


def test_chunk_with_type_fn_applies_rulebook_types():
    blocks = [
        B("text", "第三章 创建调查员", text_level="1", page_idx=0),
        B("text", "第四章 技能", text_level="1", page_idx=2),
        B("text", "会计（05%）", text_level="2", page_idx=2),
        B("text", "会计技能描述内容", text_level="", page_idx=2),
    ]
    chunks = chunk_content_list(blocks, type_fn=rulebook_type_fn)
    # 第三章（无技能关键词）→ rule；第四章 技能 及其条目 → skill
    assert chunks[0].type == "rule"
    assert chunks[0].path == "第三章 创建调查员"
    assert chunks[1].type == "skill"
    assert chunks[2].type == "skill"
    assert chunks[2].name == "会计（05%）"


def test_chunk_default_type_is_rule():
    # 不传 type_fn：通用模式，全归 rule（模组书场景）
    blocks = [B("text", "某章节", text_level="1", page_idx=0),
              B("text", "正文内容", text_level="", page_idx=0)]
    chunks = chunk_content_list(blocks)
    assert all(c.type == "rule" for c in chunks)


# ---- Chunk 序列化 -----------------------------------------------------------
def test_chunk_to_dict_fields():
    blocks = [B("text", "标题", text_level="1", page_idx=1), B("text", "正文", text_level="", page_idx=1)]
    chunks = chunk_content_list(blocks)
    d = chunks[-1].to_dict()
    assert set(["type", "name", "title", "text", "page", "start_page", "end_page",
                "path", "order", "lines"]).issubset(d.keys())
