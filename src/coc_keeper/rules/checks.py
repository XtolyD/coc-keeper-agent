# -*- coding: utf-8 -*-
"""检定与理智/幸运判定（纯函数，供 KP Agent 以工具形式调用）。

规则出处：《COC7th 核心规则书 v1.2.1》
- 第五章 游戏系统（技能检定 / 对抗 / 幸运，p70-83）
- 第八章 理智（p133-149）

关键规则（已对照规则书核实）：
- 技能检定：掷 d100。大成功=01；大失败=100（或技能<50 时 96-100）。
  达到难度阈值（常规=全值 / 困难=半值 / 极难=五分之一）即成功。
- 对抗检定：比较双方成功度（大成功>极难>困难>常规>失败>大失败）；
  平手时技能/属性高者胜；仍平手则僵局或重骰。对抗检定不可孤注一骰。
- 幸运检定：d100 ≤ 当前幸运值即成功（奖励骰/惩罚骰不适用）。
- 理智检定：d100 ≤ 当前理智即成功。损失写作“成功/失败”，如 0/1D6。
  大失败时损失失败项的最大值。
- 临时性疯狂：单一来源一次损失 ≥5 点理智 → 做 INT 检定，通过则进入
  临时性疯狂（1D10 小时）；失败则压抑记忆、不进入疯狂（与常规相反）。
- 不定性疯狂：一个游戏日内累计损失 ≥ 当前理智的 1/5。
- 永久性疯狂：理智降为 0。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from ..dice import (
    Degree, Difficulty, DEGREE_CN,
    d100, degree_of_success, difficulty_target, max_roll, roll_dice,
)


@dataclass
class CheckResult:
    """一次技能/属性检定的完整结果。"""
    roll: int
    value: int                 # 技能/属性值
    difficulty: Difficulty
    target: int                # 该难度下的成功阈值
    degree: Degree
    success: bool
    bonus_dice: int = 0
    penalty_dice: int = 0

    @property
    def degree_name(self) -> str:
        return DEGREE_CN[self.degree]


def skill_check(
    value: int,
    difficulty: Difficulty = Difficulty.REGULAR,
    bonus_dice: int = 0,
    penalty_dice: int = 0,
    rng: Optional[random.Random] = None,
) -> CheckResult:
    """掷一次技能/属性检定。"""
    rng = rng or random
    roll = d100(bonus_dice, penalty_dice, rng)
    target = difficulty_target(value, difficulty)
    deg = degree_of_success(roll, value)
    if deg == Degree.CRITICAL:
        success = True
    elif deg == Degree.FUMBLE:
        success = False
    else:
        success = roll <= target
    return CheckResult(roll, value, difficulty, target, deg, success, bonus_dice, penalty_dice)


@dataclass
class OpposedResult:
    """一次对抗检定结果。winner: "a" | "b" | "tie"。"""
    roll_a: int
    roll_b: int
    value_a: int
    value_b: int
    degree_a: Degree
    degree_b: Degree
    winner: str

    @property
    def degree_a_name(self) -> str:
        return DEGREE_CN[self.degree_a]

    @property
    def degree_b_name(self) -> str:
        return DEGREE_CN[self.degree_b]


def opposed_check(
    value_a: int,
    value_b: int,
    bonus_a: int = 0, penalty_a: int = 0,
    bonus_b: int = 0, penalty_b: int = 0,
    rng: Optional[random.Random] = None,
) -> OpposedResult:
    """对抗检定：比较双方成功度，平手时值高者胜，仍平手则僵局。"""
    rng = rng or random
    ra = d100(bonus_a, penalty_a, rng)
    rb = d100(bonus_b, penalty_b, rng)
    da = degree_of_success(ra, value_a)
    db = degree_of_success(rb, value_b)
    if da > db:
        winner = "a"
    elif db > da:
        winner = "b"
    elif value_a > value_b:
        winner = "a"
    elif value_b > value_a:
        winner = "b"
    else:
        winner = "tie"
    return OpposedResult(ra, rb, value_a, value_b, da, db, winner)


def luck_check(luck_value: int, rng: Optional[random.Random] = None) -> CheckResult:
    """幸运检定：d100 ≤ 当前幸运值即成功。"""
    rng = rng or random
    roll = d100(0, 0, rng)
    deg = degree_of_success(roll, luck_value)
    success = deg != Degree.FUMBLE and roll <= luck_value
    return CheckResult(roll, luck_value, Difficulty.REGULAR, luck_value, deg, success)


@dataclass
class SanityResult:
    """一次理智检定的结果。"""
    roll: int
    san_before: int
    success: bool
    degree: Degree
    loss: int                  # 本次损失理智点
    san_after: int

    @property
    def degree_name(self) -> str:
        return DEGREE_CN[self.degree]

    @property
    def needs_temporary_check(self) -> bool:
        """单次来源损失 ≥5 点 → 需 INT 检定判定临时性疯狂。"""
        return self.loss >= 5


def sanity_check(
    san_current: int,
    loss_success: str,
    loss_failure: str,
    rng: Optional[random.Random] = None,
) -> SanityResult:
    """理智检定。

    loss_success / loss_failure：理智损失表达式（成功 / 失败），
    例如 "0/1D6"、"1/1D6+1"、"1D10/1D100"。大失败按失败项最大值损失。
    """
    rng = rng or random
    roll = d100(0, 0, rng)
    deg = degree_of_success(roll, san_current)
    success = deg != Degree.FUMBLE and roll <= san_current
    if deg == Degree.FUMBLE:
        loss = max_roll(loss_failure)
    elif success:
        loss = max(0, roll_dice(loss_success, rng))
    else:
        loss = max(0, roll_dice(loss_failure, rng))
    return SanityResult(roll, san_current, success, deg, loss, max(0, san_current - loss))


def temporary_insanity_check(loss: int, int_value: int, rng: Optional[random.Random] = None) -> Optional[bool]:
    """临时性疯狂判定（单一来源损失 ≥5 点时调用）。

    返回：
    - None ：损失 < 5，无需判定
    - True ：INT 检定成功（掷骰 ≤ INT）→ 进入临时性疯狂（注意与常规直觉相反）
    - False：INT 检定失败 → 压抑记忆，不进入疯狂
    """
    if loss < 5:
        return None
    rng = rng or random
    roll = d100(0, 0, rng)
    return roll <= int_value


def indefinite_insanity_triggered(day_total_loss: int, san_before: int) -> bool:
    """一个游戏日内累计损失 ≥ 当前理智的 1/5 → 不定性疯狂。

    用整数安全形式表达「损失 ≥ SAN/5」，等价于 5 × 损失 ≥ SAN，
    避免除法的舍入歧义（例如 SAN=11 时 1/5≈2.2，损失 2 点尚不触发）。
    """
    return day_total_loss * 5 >= san_before
