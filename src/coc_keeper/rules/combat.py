# -*- coding: utf-8 -*-
"""CoC 7th 战斗与伤害结算。

规则层保持纯函数风格：攻击者和目标是简单数据类，随机源显式传入，
因此战斗回合可以在评估和存档恢复后精确重放。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..dice import Degree, Difficulty, max_roll, roll_dice
from .checks import CheckResult, OpposedResult, opposed_check, skill_check


class RangeBand(str, Enum):
    BASE = "base"
    LONG = "long"
    EXTREME = "extreme"


@dataclass(frozen=True)
class Weapon:
    name: str
    damage: str
    skill: str = "格斗（斗殴）"
    armor_piercing: bool = False


@dataclass
class Combatant:
    name: str
    hp: int
    hp_max: int
    dex: int = 50
    armor: int = 0
    db: str = "0"
    build: int = 0
    unconscious: bool = False
    dead: bool = False


@dataclass(frozen=True)
class DamageResult:
    rolled: int
    armor: int
    damage: int
    hp_after: int
    major_wound: bool
    unconscious: bool
    dead: bool


@dataclass(frozen=True)
class AttackResult:
    attacker: str
    defender: str
    attack: CheckResult
    damage: Optional[DamageResult]
    hit: bool


@dataclass(frozen=True)
class MeleeResult:
    opposed: OpposedResult
    damage: Optional[DamageResult]
    hit: bool


def apply_damage(
    target: Combatant,
    amount: int,
    *,
    armor: Optional[int] = None,
) -> DamageResult:
    """扣除护甲并更新目标状态。

    单次伤害达到目标最大 HP 的一半即为重伤；HP 降到 0 时失去意识，
    若同时为重伤则视为濒死（此处以 ``dead`` 标记供上层决定急救窗口）。
    """
    absorbed = max(0, target.armor if armor is None else armor)
    damage = max(0, int(amount) - absorbed)
    target.hp = max(0, target.hp - damage)
    major = damage > 0 and damage * 2 >= max(1, target.hp_max)
    if target.hp == 0:
        target.unconscious = True
        target.dead = major
    return DamageResult(
        rolled=int(amount), armor=absorbed, damage=damage, hp_after=target.hp,
        major_wound=major, unconscious=target.unconscious, dead=target.dead,
    )


def heal(target: Combatant, amount: int) -> int:
    """恢复 HP，不超过最大值；返回治疗后的 HP。"""
    target.hp = min(target.hp_max, target.hp + max(0, int(amount)))
    if target.hp > 0:
        target.unconscious = False
        target.dead = False
    return target.hp


def resolve_attack(
    attacker: Combatant,
    defender: Combatant,
    attack_value: int,
    weapon: Weapon,
    *,
    difficulty: Difficulty = Difficulty.REGULAR,
    bonus_dice: int = 0,
    penalty_dice: int = 0,
    rng: Optional[random.Random] = None,
) -> AttackResult:
    """完成一次攻击检定并在命中时结算伤害。"""
    rng = rng or random
    check = skill_check(attack_value, difficulty, bonus_dice, penalty_dice, rng)
    if not check.success:
        return AttackResult(attacker.name, defender.name, check, None, False)
    db = attacker.db if str(attacker.db).startswith(("+", "-")) else f"+{attacker.db}"
    damage_expr = f"{weapon.damage}{db}"
    rolled = roll_dice(damage_expr, rng)
    if check.degree == Degree.CRITICAL:
        rolled = max_roll(weapon.damage) + roll_dice(attacker.db, rng)
    damage = apply_damage(defender, rolled, armor=0 if weapon.armor_piercing else None)
    return AttackResult(attacker.name, defender.name, check, damage, True)


def combat_round(
    attacker: Combatant,
    defender: Combatant,
    attack_value: int,
    weapon: Weapon,
    *,
    rng: Optional[random.Random] = None,
) -> AttackResult:
    """语义化别名：执行一个战斗轮中的单次攻击。"""
    return resolve_attack(attacker, defender, attack_value, weapon, rng=rng)


def resolve_melee(
    attacker: Combatant,
    defender: Combatant,
    attacker_value: int,
    defender_value: int,
    weapon: Weapon,
    *,
    rng: Optional[random.Random] = None,
) -> MeleeResult:
    """近战双方对抗；只有攻击方赢得对抗时结算伤害。"""
    rng = rng or random
    opposed = opposed_check(attacker_value, defender_value, rng=rng)
    if opposed.winner != "a":
        return MeleeResult(opposed, None, False)
    db = attacker.db if str(attacker.db).startswith(("+", "-")) else f"+{attacker.db}"
    rolled = roll_dice(f"{weapon.damage}{db}", rng)
    if opposed.degree_a == Degree.CRITICAL:
        rolled = max_roll(weapon.damage) + roll_dice(attacker.db, rng)
    damage = apply_damage(defender, rolled)
    return MeleeResult(opposed, damage, True)


def resolve_firearm_attack(
    attacker: Combatant,
    defender: Combatant,
    attack_value: int,
    weapon: Weapon,
    *,
    range_band: RangeBand = RangeBand.BASE,
    cover_penalty: int = 0,
    rng: Optional[random.Random] = None,
) -> AttackResult:
    """射击检定：远距离为困难，极远距离为极难，掩体增加惩罚骰。"""
    difficulty = {
        RangeBand.BASE: Difficulty.REGULAR,
        RangeBand.LONG: Difficulty.HARD,
        RangeBand.EXTREME: Difficulty.EXTREME,
    }[RangeBand(range_band)]
    return resolve_attack(
        attacker, defender, attack_value, weapon, difficulty=difficulty,
        penalty_dice=max(0, int(cover_penalty)), rng=rng,
    )
