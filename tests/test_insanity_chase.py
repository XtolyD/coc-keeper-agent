# -*- coding: utf-8 -*-
from coc_keeper.rules.chase import ChaseParticipant, ChaseState, advance_chase
from coc_keeper.rules.insanity import InsanityState, InsanityTracker


def test_temporary_insanity_state(scripted):
    tracker = InsanityTracker()
    event = tracker.record_loss(6, 80, 50, rng=scripted(0, 3, 4))
    assert event.state_after == InsanityState.TEMPORARY
    assert tracker.temporary_hours == 4
    tracker.recover_temporary()
    assert tracker.state == InsanityState.STABLE


def test_indefinite_and_permanent_insanity(scripted):
    tracker = InsanityTracker()
    event = tracker.record_loss(10, 50, 40, rng=scripted(0, 8))
    assert event.state_after == InsanityState.INDEFINITE
    tracker = InsanityTracker()
    event = tracker.record_loss(10, 10, 40, rng=scripted(0, 8))
    assert event.state_after == InsanityState.PERMANENT


def test_indefinite_threshold_uses_day_start_san():
    tracker = InsanityTracker()
    assert tracker.record_loss(4, 50, 40).state_after == InsanityState.STABLE
    assert tracker.record_loss(4, 46, 40).state_after == InsanityState.STABLE
    assert tracker.record_loss(2, 42, 40).state_after == InsanityState.INDEFINITE
    assert tracker.day_start_san == 50
    tracker.new_day()
    assert tracker.day_start_san == 0


def test_chase_orders_and_finishes():
    slow = ChaseParticipant("慢者", mov=7)
    fast = ChaseParticipant("快者", mov=9)
    state = ChaseState([slow, fast], distance_to_goal=9)
    advance_chase(state)
    assert state.round == 1
    assert state.finished == "快者"
    assert fast.position == 9
    assert slow.position == 7


def test_chase_obstacle_can_exhaust():
    runner = ChaseParticipant("跑者", mov=8)
    state = ChaseState([runner])
    advance_chase(state, obstacles=[10])
    assert runner.position == 0
    assert runner.exhausted is True
