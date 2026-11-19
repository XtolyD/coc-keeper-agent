# -*- coding: utf-8 -*-
"""CoC 7th 版骰子机制（纯函数、无副作用、便于测试）。

规则出处：《COC7th 核心规则书 v1.2.1》
- 第一章 1.6.1 骰子
- 第五章 游戏系统（p70-83）
- 附录「游戏系统摘要」（p358）

核心事实（已对照规则书核实）：
- 百分骰 d100 结果为 1..100（十位骰 0 + 个位骰 0 记作 100）。
- 大成功：掷出 01。
- 大失败：掷出 100 总是大失败；若技能/属性 < 50，则 96-100 均为大失败。
- 奖励骰：额外掷十位骰，取较小的完整百分骰结果；惩罚骰：取较大结果。
- 难度：常规 = 全值；困难 = 半值（向下取整）；极难 = 五分之一值（向下取整）。
"""
from __future__ import annotations

import random
import re
from enum import IntEnum
from typing import Optional


class Difficulty(IntEnum):
    """检定难度等级。"""
    REGULAR = 1   # 常规难度
    HARD = 2      # 困难难度（半值）
    EXTREME = 3   # 极难难度（五分之一值）


class Degree(IntEnum):
    """成功度（自然阈值判定），数值越大越好，用于对抗检定比较。"""
    FUMBLE = 0     # 大失败
    FAIL = 1       # 失败
    REGULAR = 2    # 常规成功
    HARD = 3       # 困难成功（≤ 半值）
    EXTREME = 4    # 极难成功（≤ 五分之一值）
    CRITICAL = 5   # 大成功（01）


DEGREE_CN = {
    Degree.FUMBLE: "大失败",
    Degree.FAIL: "失败",
    Degree.REGULAR: "常规成功",
    Degree.HARD: "困难成功",
    Degree.EXTREME: "极难成功",
    Degree.CRITICAL: "大成功",
}


def half(value: int) -> int:
    """半值（困难难度阈值）。"""
    return value // 2


def fifth(value: int) -> int:
    """五分之一值（极难难度阈值）。"""
    return value // 5


def difficulty_target(value: int, difficulty: Difficulty) -> int:
    """某难度等级下的成功阈值。"""
    if difficulty == Difficulty.HARD:
        return half(value)
    if difficulty == Difficulty.EXTREME:
        return fifth(value)
    return value


def _to_halfwidth(expr: str) -> str:
    """把全角数字/符号转半角，避免 LLM 输出全角导致解析失败。"""
    full = "０１２３４５６７８９ｄＤ＋－　"
    half_ = "0123456789dD+- "
    return expr.translate(str.maketrans(full, half_))


def _parse_terms(expr: str) -> list[str]:
    normalized = _to_halfwidth(expr).replace(" ", "").replace("\u3000", "").lower()
    if not normalized:
        raise ValueError("骰表达式为空")
    if not re.fullmatch(r"[+-]?\d+(?:d\d+)?(?:[+-]\d+(?:d\d+)?)*", normalized):
        raise ValueError(f"无法解析骰表达式: {expr!r}")
    terms = re.findall(r"[+-]?\d+d\d+|[+-]?\d+", normalized)
    for term in terms:
        raw = term.lstrip("+-")
        if "d" in raw:
            count, sides = map(int, raw.split("d"))
            if not 1 <= count <= 1000 or not 1 <= sides <= 100000:
                raise ValueError("骰子数量必须为 1..1000，面数必须为 1..100000")
    return terms


def d(sides: int, rng: Optional[random.Random] = None) -> int:
    """掷一个 sides 面骰，返回 1..sides。"""
    rng = rng or random
    return rng.randint(1, sides)


def roll_dice(expr: str, rng: Optional[random.Random] = None) -> int:
    """解析并掷骰表达式，返回总和。

    支持 XdY、常数，以及 + / - 连接，例如：
        "1d6"       -> 1..6
        "1d6+1d4+2" -> 各项之和
        "2d10+1"    -> 2d10 再加 1
        "1d6-1"     -> 1d6 再减 1
        "0" / "1"   -> 常数（用于理智损失 "0/1D6" 中的 0）
    """
    rng = rng or random
    total = 0
    for tok in _parse_terms(expr):
        sign = 1
        if tok[0] in "+-":
            if tok[0] == "-":
                sign = -1
            tok = tok[1:]
        if "d" in tok.lower():
            n, s = tok.lower().split("d")
            n = int(n) if n else 1
            total += sign * sum(rng.randint(1, int(s)) for _ in range(n))
        else:
            total += sign * int(tok)
    return total


def max_roll(expr: str) -> int:
    """计算骰表达式可能的最大值，例如 1d6+1 -> 7，1d100 -> 100。"""
    total = 0
    for tok in _parse_terms(expr):
        sign = 1
        if tok[0] in "+-":
            if tok[0] == "-":
                sign = -1
            tok = tok[1:]
        if "d" in tok.lower():
            n, s = tok.lower().split("d")
            n = int(n) if n else 1
            total += n * int(s) if sign > 0 else -n
        else:
            total += sign * int(tok)
    return total


def d100(bonus_dice: int = 0, penalty_dice: int = 0, rng: Optional[random.Random] = None) -> int:
    """掷百分骰（1..100），支持奖励骰 / 惩罚骰（二者先相互抵消）。"""
    rng = rng or random
    net = bonus_dice - penalty_dice
    units = rng.randint(0, 9)
    tens_digits = [rng.randint(0, 9) for _ in range(1 + abs(net))]
    # 个位为 0 时，00 表示 100，必须先换算再比较好坏。
    results = [tens * 10 + units or 100 for tens in tens_digits]
    if net > 0:
        return min(results)
    elif net < 0:
        return max(results)
    return results[0]


def degree_of_success(roll: int, value: int) -> Degree:
    """根据掷骰结果与技能/属性值判定自然成功度（与难度等级无关）。"""
    if roll == 1:
        return Degree.CRITICAL
    if roll == 100 or (value < 50 and roll >= 96):
        return Degree.FUMBLE
    if roll <= fifth(value):
        return Degree.EXTREME
    if roll <= half(value):
        return Degree.HARD
    if roll <= value:
        return Degree.REGULAR
    return Degree.FAIL
