# -*- coding: utf-8 -*-
import random

from coc_keeper.dice import (
    Difficulty, d100, degree_of_success, difficulty_target,
    fifth, half, max_roll, roll_dice,
)


def test_half_fifth_round_down():
    assert half(50) == 25
    assert fifth(50) == 10
    assert half(45) == 22   # 向下取整
    assert fifth(45) == 9


def test_difficulty_target():
    assert difficulty_target(50, Difficulty.REGULAR) == 50
    assert difficulty_target(50, Difficulty.HARD) == 25
    assert difficulty_target(50, Difficulty.EXTREME) == 10


def test_roll_dice_constants_and_range():
    rng = random.Random(1)
    assert roll_dice("0", rng) == 0
    assert roll_dice("1", rng) == 1
    assert roll_dice("1d6-1", rng) in range(0, 6)  # 0..5
    for _ in range(200):
        assert 1 <= roll_dice("1d6", rng) <= 6
        assert 3 <= roll_dice("1d6+2", rng) <= 8
        assert 2 <= roll_dice("2d10", rng) <= 20


def test_roll_dice_fullwidth_normalized():
    rng = random.Random(3)
    assert 1 <= roll_dice("１ｄ６＋２", rng) <= 8  # 全角应被归一化


def test_max_roll():
    assert max_roll("1d6") == 6
    assert max_roll("1d6+1") == 7
    assert max_roll("2d10+1") == 21
    assert max_roll("1d100") == 100
    assert max_roll("0") == 0


def test_d100_range():
    rng = random.Random(2)
    for _ in range(5000):
        assert 1 <= d100(rng=rng) <= 100


def test_d100_zero_maps_to_100(scripted):
    rng = scripted(0, 0)  # units=0, tens=0
    assert d100(rng=rng) == 100


def test_d100_bonus_takes_lower_tens(scripted):
    rng = scripted(5, 7, 2)  # units=5, 两个十位 7 与 2 -> 取较小 2
    assert d100(bonus_dice=1, rng=rng) == 25


def test_d100_penalty_takes_higher_tens(scripted):
    rng = scripted(5, 7, 2)  # units=5, 两个十位 7 与 2 -> 取较大 7
    assert d100(penalty_dice=1, rng=rng) == 75


def test_degree_of_success_thresholds():
    # 技能 50：半值 25，五分之一 10
    assert degree_of_success(1, 50).name == "CRITICAL"
    assert degree_of_success(10, 50).name == "EXTREME"
    assert degree_of_success(25, 50).name == "HARD"
    assert degree_of_success(50, 50).name == "REGULAR"
    assert degree_of_success(51, 50).name == "FAIL"
    # 技能 >= 50：大失败仅 100
    assert degree_of_success(99, 60).name == "FAIL"
    assert degree_of_success(100, 60).name == "FUMBLE"
    # 技能 < 50：96-100 都是大失败
    assert degree_of_success(96, 40).name == "FUMBLE"
    assert degree_of_success(95, 40).name == "FAIL"
