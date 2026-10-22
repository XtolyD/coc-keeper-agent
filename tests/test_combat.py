# -*- coding: utf-8 -*-
from coc_keeper.rules.combat import (
    Combatant, RangeBand, Weapon, apply_damage, heal,
    resolve_attack, resolve_firearm_attack, resolve_melee,
)


def test_damage_armor_and_major_wound():
    target = Combatant("食尸鬼", hp=10, hp_max=11, armor=2)
    result = apply_damage(target, 7)
    assert result.damage == 5
    assert result.hp_after == 5
    assert result.major_wound is False  # 5 < 11 / 2


def test_damage_zero_hp_and_major_wound():
    target = Combatant("邪教徒", hp=4, hp_max=10)
    result = apply_damage(target, 6)
    assert result.hp_after == 0
    assert result.major_wound is True
    assert result.unconscious is True
    assert result.dead is True


def test_resolve_attack_hit(scripted):
    attacker = Combatant("调查员", hp=10, hp_max=10, db="0")
    target = Combatant("目标", hp=8, hp_max=8, armor=1)
    result = resolve_attack(attacker, target, 60, Weapon("短棍", "1d6"), rng=scripted(0, 2, 4))
    assert result.hit is True
    assert result.attack.roll == 20
    assert result.damage.damage == 3
    assert target.hp == 5


def test_resolve_attack_miss_has_no_damage(scripted):
    attacker = Combatant("调查员", hp=10, hp_max=10)
    target = Combatant("目标", hp=8, hp_max=8)
    result = resolve_attack(attacker, target, 20, Weapon("短棍", "1d6"), rng=scripted(0, 8))
    assert result.hit is False
    assert result.damage is None
    assert target.hp == 8


def test_melee_opposed_and_healing(scripted):
    attacker = Combatant("甲", 10, 10, db="0")
    defender = Combatant("乙", 8, 8)
    # 甲 20（困难成功），乙 40（常规成功），随后伤害 3。
    result = resolve_melee(attacker, defender, 60, 50, Weapon("棍", "1d4"), rng=scripted(0, 2, 0, 4, 3))
    assert result.hit is True
    assert defender.hp == 5
    assert heal(defender, 10) == 8


def test_firearm_range_sets_difficulty(scripted):
    attacker = Combatant("甲", 10, 10)
    defender = Combatant("乙", 8, 8)
    result = resolve_firearm_attack(
        attacker, defender, 60, Weapon("步枪", "1d6", "射击（步枪/霰弹枪）"),
        range_band=RangeBand.LONG, rng=scripted(0, 4),
    )
    assert result.attack.target == 30
    assert result.hit is False
