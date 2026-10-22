# -*- coding: utf-8 -*-
"""可复现的规则层验收场景。"""
from __future__ import annotations

import random

from .rules.checks import sanity_check
from .rules.combat import Combatant, Weapon, heal, resolve_attack
from .rules.insanity import InsanityTracker


def run_ghoul_encounter(seed: int = 7) -> dict:
    """遭遇食尸鬼、理智检定、战斗和治疗的离线端到端模拟。"""
    rng = random.Random(seed)
    investigator = Combatant("调查员", hp=12, hp_max=12, dex=60, db="+1d4")
    ghoul = Combatant("食尸鬼", hp=8, hp_max=8, dex=55, armor=1)
    sanity = sanity_check(60, "1", "1d6", rng=rng)
    tracker = InsanityTracker()
    insanity = tracker.record_loss(sanity.loss, sanity.san_before, 70, rng=rng)
    rounds: list[dict] = []
    weapon = Weapon("左轮手枪", "1d10", "射击（手枪）")
    for round_number in range(1, 11):
        attack = resolve_attack(investigator, ghoul, 75, weapon, rng=rng)
        rounds.append({
            "round": round_number,
            "hit": attack.hit,
            "roll": attack.attack.roll,
            "damage": attack.damage.damage if attack.damage else 0,
            "ghoul_hp": ghoul.hp,
        })
        if ghoul.hp == 0:
            break
    investigator.hp -= 3
    hp_after_injury = investigator.hp
    hp_after_healing = heal(investigator, 2)
    return {
        "sanity": {"before": sanity.san_before, "loss": sanity.loss, "after": sanity.san_after},
        "insanity": insanity.state_after.value,
        "combat": rounds,
        "ghoul_defeated": ghoul.hp == 0,
        "healing": {"before": hp_after_injury, "after": hp_after_healing},
    }
