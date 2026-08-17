# -*- coding: utf-8 -*-
import random

from coc_keeper.character import (
    Attributes, CharacterSheet, base_skill_values,
    create_character, damage_bonus_and_build, movement,
)


def test_damage_bonus_table():
    cases = [
        (64, "-2", -2),
        (65, "-1", -1),
        (84, "-1", -1),
        (85, "0", 0),
        (124, "0", 0),
        (125, "+1d4", 1),
        (164, "+1d4", 1),
        (165, "+1d6", 2),
        (204, "+1d6", 2),
        (205, "+2d6", 3),
        (285, "+3d6", 4),
        (445, "+5d6", 6),
        (524, "+5d6", 6),
    ]
    for s, db, build in cases:
        assert damage_bonus_and_build(s) == (db, build), f"STR+SIZ={s}"


def test_damage_bonus_overflow():
    # 超过 524：每超 80（不足 80 按 80 算）额外 +1d6 与 +1 体格
    assert damage_bonus_and_build(525) == ("+6d6", 7)


def test_derived_stats():
    a = Attributes(STR=50, CON=60, DEX=50, APP=50, POW=50, SIZ=50, INT=60, EDU=60, LUCK=50)
    sheet = CharacterSheet(attributes=a)
    assert sheet.hp_max == (60 + 50) // 10
    assert sheet.mp_max == 50 // 5
    assert sheet.san_max == 50
    assert sheet.hp == sheet.hp_max       # 默认当前值 = 上限
    assert sheet.mp == sheet.mp_max
    assert sheet.san == sheet.san_max
    assert sheet.luck == 50


def test_movement():
    assert movement(STR=70, DEX=70, SIZ=50, age=30) == 9   # 两者都大于体型
    assert movement(STR=40, DEX=40, SIZ=60, age=30) == 7   # 两者都小于体型
    assert movement(STR=70, DEX=40, SIZ=50, age=30) == 8   # 其它
    assert movement(STR=70, DEX=70, SIZ=50, age=55) == 7   # 50-59 岁 -2


def test_skill_base_derived():
    a = Attributes(DEX=60, EDU=70)
    bases = base_skill_values(a)
    assert bases["闪避"] == 30   # DEX/2
    assert bases["母语"] == 70   # EDU
    assert bases["侦查"] == 25   # 固定基础值


def test_create_character_ranges():
    c = create_character("哈维", rng=random.Random(7))
    assert c.name == "哈维"
    assert c.hp == c.hp_max
    for attr in ["STR", "CON", "DEX", "APP", "POW"]:
        assert 15 <= getattr(c.attributes, attr) <= 90
    for attr in ["SIZ", "INT", "EDU"]:
        assert 40 <= getattr(c.attributes, attr) <= 90
    assert 15 <= c.attributes.LUCK <= 90
