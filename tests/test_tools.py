# -*- coding: utf-8 -*-
import random

import pytest

from coc_keeper.agent.state import Session
from coc_keeper.agent.tools import make_dispatcher
from coc_keeper.character import CharacterSheet
from coc_keeper.retrieval import Index
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleScene
from coc_keeper.rules.insanity import InsanityState, InsanityTracker


def test_dispatcher_search_and_skill_update(scripted):
    index = Index.build([
        {"name": "", "text": "奖励骰取较小的十位骰。", "page": 70,
         "start_page": 70, "end_page": 70, "path": "", "lines": ["奖励骰取较小的十位骰。"]}
    ])
    session = Session()
    dispatch = make_dispatcher(session, rule_index=index, rng=scripted())
    result = dispatch("search_rules", {"query": "奖励骰"})
    assert result["hits"][0]["page"] == 70
    updated = dispatch("set_skill", {"skill": "侦查", "value": 200})
    assert updated["数值"] == 100
    assert session.investigator.skills["侦查"] == 100


def test_dispatcher_rejects_bad_arguments():
    dispatch = make_dispatcher(Session())
    assert "error" in dispatch("missing", {})
    assert "error" in dispatch("get_character", "[]")


def test_dispatcher_module_is_current_scene_only():
    session = Session()
    session.module = ModuleRuntime(KeeperModule("模组", "module.pdf", [
        ModuleScene("scene-001", "当前", "场景 1", 1, 1, "当前线索是钥匙。"),
        ModuleScene("scene-002", "未来", "场景 2", 2, 2, "未来秘密是医生。"),
    ]))
    dispatch = make_dispatcher(session)
    result = dispatch("search_module", {"query": "医生"})
    assert "当前线索" in str(result)
    assert "未来秘密" not in str(result)
    advanced = dispatch("advance_module", {"reason": "玩家已打开门"})
    assert advanced["scene"] == "未来"


@pytest.mark.parametrize("invalid_field", ["delta_hp", "delta_mp", "delta_san", "delta_luck"])
def test_update_character_bad_increment_leaves_all_state_unchanged(invalid_field):
    session = Session(investigator=CharacterSheet(hp=10, mp=10, san=50, luck=50))
    dispatch = make_dispatcher(session)
    before = session.investigator.to_dict()
    arguments = dict(delta_hp=-3, delta_mp=-2, delta_san=-1, delta_luck=-4)
    arguments[invalid_field] = "bad"

    assert "error" in dispatch("update_character", arguments)
    assert session.investigator.to_dict() == before


def test_update_character_applies_all_changes_and_clamps_limits():
    session = Session(investigator=CharacterSheet(hp=10, mp=10, san=50, luck=50))
    dispatch = make_dispatcher(session)

    result = dispatch("update_character", dict(delta_hp=-20, delta_mp=20, delta_san=60, delta_luck=-60))

    assert "error" not in result
    assert (session.investigator.hp, session.investigator.mp, session.investigator.san, session.investigator.luck) == (0, 10, 99, 0)


@pytest.mark.parametrize("new_name", ["新调查员", "旧调查员"])
def test_create_character_resets_current_character_insanity_state(new_name):
    old = CharacterSheet(name="旧调查员", san=0)
    session = Session(investigator=old, insanity=InsanityTracker(
        state=InsanityState.PERMANENT, day_total_loss=50, day_start_san=50, temporary_hours=3,
    ))
    dispatch = make_dispatcher(session, rng=random.Random(2))

    result = dispatch("create_character", {"name": new_name})

    assert "error" not in result
    assert session.investigator.name == new_name
    assert dispatch("get_character", {})["name"] == new_name
    assert session.investigator is not old
    assert session.insanity == InsanityTracker()
    checked = dispatch("sanity_check", {"loss_success": "0", "loss_failure": "0"})
    assert checked["疯狂状态"] == "stable"
    assert checked["当前理智"] > 0


def test_character_tools_share_current_investigator():
    session = Session(investigator=CharacterSheet(name="调查员", hp=10))
    dispatch = make_dispatcher(session)
    assert dispatch("set_skill", {"skill": "侦查", "value": 80})["调查员"] == "调查员"
    dispatch("update_character", {"delta_hp": -3})
    current = dispatch("get_character", {})
    assert current["skills"]["侦查"] == 80
    assert current["current"]["hp"] == 7
    restored = Session.from_dict(session.to_dict())
    assert restored.investigator.to_dict() == current


@pytest.mark.parametrize("difficulty,digits,outcome,natural", [
    ("hard", (0, 4), False, "常规成功"),
    ("hard", (0, 2), True, "困难成功"),
    ("extreme", (0, 2), False, "困难成功"),
    ("extreme", (0, 1), True, "极难成功"),
])
def test_skill_check_distinguishes_action_outcome_from_natural_degree(scripted, difficulty, digits, outcome, natural):
    session = Session(investigator=CharacterSheet(skills={"侦查": 50}))
    dispatch = make_dispatcher(session, rng=scripted(*digits))

    result = dispatch("roll_skill_check", {"skill": "侦查", "difficulty": difficulty})

    assert result["成功"] is outcome
    assert result["行动结果"] == ("成功" if outcome else "失败")
    assert result["自然成功度"] == natural
    assert result["结果"] == natural  # 兼容已有工具结果消费者。
