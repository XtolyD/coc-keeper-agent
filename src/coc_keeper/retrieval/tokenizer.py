# -*- coding: utf-8 -*-
"""规则书检索的 tokenizer：字级 unigram + 全角归一。

设计（见 docs/retrieval-spec.md §4.2）：
- 中文逐字切分（unigram），英文/数字按连续 ASCII 串切为一个 token。
- 全角→半角归一、去空白（含全角空格）。
- 纯函数、零依赖、可测。

示例：
    tokenize("奖励骰怎么投 1D100") -> ["奖", "励", "骰", "怎", "么", "投", "1d100"]
    tokenize("STR 90 （5D6×5）")   -> ["str90", "5d6", "5"]
"""
from __future__ import annotations

import re

# 全角 → 半角映射（含数字/字母/常用标点）
_FW2HW = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ，。：；！？（）“”‘’",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz,.:;!?()\"\"''",
)

# 分词正则：连续 ASCII（字母数字）+ 单个汉字，其余（空白/符号）跳过。
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def normalize(text: str) -> str:
    """全角→半角，仅去**全角**空白（保留普通空格作为 token 分隔）。"""
    # 先把全角空格换成普通空格，再去除首尾空白，但保住词间空格
    half = text.translate(_FW2HW)
    half = half.replace("\u3000", " ")
    return half.strip()


def tokenize(text: str) -> list[str]:
    """把一段文本切成 token 列表（全角已归一、小写化）。

    空白作为 token 分隔（不把两个词合并）；中文逐字，ascii/数字连续为一词。
    """
    normalized = normalize(text)
    return [t.lower() for t in _TOKEN_RE.findall(normalized)]
