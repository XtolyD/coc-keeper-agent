# -*- coding: utf-8 -*-
"""简化追逐规则：按 MOV 排序，每轮推进距离并处理障碍。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ChaseParticipant:
    name: str
    mov: int
    position: int = 0
    exhausted: bool = False


@dataclass
class ChaseState:
    participants: list[ChaseParticipant] = field(default_factory=list)
    round: int = 0
    distance_to_goal: int = 100
    finished: str | None = None

    def ordered(self) -> list[ChaseParticipant]:
        return sorted(self.participants, key=lambda p: (-p.mov, p.name))


def advance_chase(state: ChaseState, *, obstacles: Iterable[int] = ()) -> ChaseState:
    """推进一轮追逐；obstacles 为本轮各参与者额外消耗的移动点。"""
    obstacle_cost = list(obstacles)
    state.round += 1
    for index, participant in enumerate(state.ordered()):
        cost = obstacle_cost[index] if index < len(obstacle_cost) else 0
        step = max(0, participant.mov - max(0, int(cost)))
        participant.position += step
        participant.exhausted = step == 0
        if participant.position >= state.distance_to_goal and state.finished is None:
            state.finished = participant.name
    return state
