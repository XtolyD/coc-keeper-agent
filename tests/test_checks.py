# -*- coding: utf-8 -*-
from coc_keeper.dice import Degree, Difficulty
from coc_keeper.rules.checks import (
    indefinite_insanity_triggered, luck_check, opposed_check,
    sanity_check, skill_check, temporary_insanity_check,
)


def test_skill_check_regular_success(scripted):
    rng = scripted(5, 2)  # d100 -> 25
    r = skill_check(50, rng=rng)
    assert r.roll == 25
    assert r.degree == Degree.HARD
    assert r.success is True


def test_skill_check_hard_difficulty(scripted):
    rng = scripted(5, 2)  # 25
    r = skill_check(50, difficulty=Difficulty.HARD, rng=rng)
    assert r.target == 25
    assert r.success is True   # 25 <= 25

    rng = scripted(6, 2)  # 26
    r = skill_check(50, difficulty=Difficulty.HARD, rng=rng)
    assert r.success is False  # 26 > 25


def test_skill_check_extreme_fail(scripted):
    rng = scripted(5, 2)  # 25
    r = skill_check(50, difficulty=Difficulty.EXTREME, rng=rng)
    assert r.target == 10
    assert r.success is False  # 25 > 10


def test_skill_check_critical_always_succeeds(scripted):
    rng = scripted(1, 0)  # d100 -> 1
    r = skill_check(10, difficulty=Difficulty.EXTREME, rng=rng)
    assert r.degree == Degree.CRITICAL
    assert r.success is True


def test_skill_check_fumble(scripted):
    rng = scripted(6, 9)  # d100 -> 96
    r = skill_check(40, rng=rng)
    assert r.degree == Degree.FUMBLE
    assert r.success is False


def test_opposed_check_higher_degree_wins(scripted):
    # a: 30 (units=0,tens=3) 值60 -> 困难成功(半值30)；b: 35 (units=5,tens=3) 值40 -> 常规成功
    rng = scripted(0, 3, 5, 3)
    r = opposed_check(60, 40, rng=rng)
    assert r.degree_a == Degree.HARD
    assert r.degree_b == Degree.REGULAR
    assert r.winner == "a"


def test_opposed_check_tie_higher_value_wins(scripted):
    rng = scripted(0, 4, 0, 4)  # 双方都 40
    r = opposed_check(60, 50, rng=rng)
    assert r.degree_a == r.degree_b
    assert r.winner == "a"  # 60 > 50


def test_opposed_check_equal_tie(scripted):
    rng = scripted(0, 4, 0, 4)
    r = opposed_check(50, 50, rng=rng)
    assert r.winner == "tie"


def test_luck_check(scripted):
    rng = scripted(0, 3)  # 30
    assert luck_check(50, rng=rng).success is True
    rng = scripted(0, 6)  # 60
    assert luck_check(50, rng=rng).success is False


def test_sanity_check_success_no_loss(scripted):
    rng = scripted(0, 3)  # d100 -> 30，成功
    r = sanity_check(50, "0", "1d6", rng=rng)
    assert r.success is True
    assert r.loss == 0
    assert r.san_after == 50


def test_sanity_check_fail_loss(scripted):
    rng = scripted(0, 6, 3)  # d100 -> 60 失败；随后 1d6 -> 3
    r = sanity_check(50, "1", "1d6+1", rng=rng)
    assert r.success is False
    assert r.loss == 4  # 1d6+1 -> 3+1
    assert r.san_after == 46


def test_sanity_check_fumble_loses_max(scripted):
    rng = scripted(0, 0)  # d100 -> 100 大失败
    r = sanity_check(50, "0", "1d6", rng=rng)
    assert r.degree == Degree.FUMBLE
    assert r.loss == 6  # 失败项最大值
    assert r.needs_temporary_check is True  # >= 5


def test_sanity_never_drops_below_zero(scripted):
    rng = scripted(0, 0)  # 大失败，失败损失取最大值 100
    r = sanity_check(3, "0", "1d100", rng=rng)
    assert r.san_after == 0


def test_temporary_insanity_check(scripted):
    assert temporary_insanity_check(4, 50) is None  # 损失不足 5
    rng = scripted(0, 3)  # INT 检定 -> 30
    assert temporary_insanity_check(6, 50, rng=rng) is True   # 通过 -> 进入疯狂
    rng = scripted(0, 6)  # INT 检定 -> 60
    assert temporary_insanity_check(6, 50, rng=rng) is False  # 失败 -> 压抑记忆


def test_indefinite_insanity_triggered():
    assert indefinite_insanity_triggered(10, 50) is True    # 10 >= 50/5
    assert indefinite_insanity_triggered(9, 50) is False
    assert indefinite_insanity_triggered(2, 10) is True     # 2 >= 10/5
    assert indefinite_insanity_triggered(1, 10) is False    # 1 < 10/5
    assert indefinite_insanity_triggered(1, 4) is True      # SAN=4：1 >= 4/5
