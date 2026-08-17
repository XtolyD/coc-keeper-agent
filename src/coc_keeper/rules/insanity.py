# -*- coding: utf-8 -*-
"""理智损失驱动的疯狂状态机。"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .checks import indefinite_insanity_triggered, temporary_insanity_check


class InsanityState(str, Enum):
    STABLE = "stable"
    TEMPORARY = "temporary"
    INDEFINITE = "indefinite"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class InsanityEvent:
    state_before: InsanityState
    state_after: InsanityState
    loss: int
    temporary_check: Optional[bool]
    day_total_loss: int
    reason: str


@dataclass
class InsanityTracker:
    """追踪单个调查员的游戏日理智损失和疯狂状态。"""
    state: InsanityState = InsanityState.STABLE
    day_total_loss: int = 0
    temporary_hours: int = 0
    day_start_san: int = 0

    def record_loss(
        self,
        loss: int,
        san_before: int,
        int_value: int,
        *,
        rng: Optional[random.Random] = None,
    ) -> InsanityEvent:
        rng = rng or random
        loss = max(0, int(loss))
        before = self.state
        if self.day_start_san <= 0:
            self.day_start_san = max(0, int(san_before))
        self.day_total_loss += loss
        temp_check = temporary_insanity_check(loss, int_value, rng)
        reason = "理智损失"
        if san_before - loss <= 0:
            self.state = InsanityState.PERMANENT
            reason = "理智降至 0"
        elif self.state in (InsanityState.STABLE, InsanityState.TEMPORARY) and indefinite_insanity_triggered(
            self.day_total_loss, self.day_start_san
        ):
            self.state = InsanityState.INDEFINITE
            reason = "单日累计理智损失达到五分之一"
        elif self.state == InsanityState.STABLE and temp_check is True:
            self.state = InsanityState.TEMPORARY
            self.temporary_hours = rng.randint(1, 10)
            reason = "INT 检定成功，进入临时性疯狂"
        return InsanityEvent(before, self.state, loss, temp_check, self.day_total_loss, reason)

    def new_day(self) -> None:
        self.day_total_loss = 0
        self.day_start_san = 0

    def recover_temporary(self) -> None:
        if self.state == InsanityState.TEMPORARY:
            self.state = InsanityState.STABLE
            self.temporary_hours = 0

    def recover_indefinite(self) -> None:
        if self.state == InsanityState.INDEFINITE:
            self.state = InsanityState.STABLE
