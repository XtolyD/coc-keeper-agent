# -*- coding: utf-8 -*-
from coc_keeper.agent.state import Session
from coc_keeper.agent.tools import make_dispatcher
from coc_keeper.retrieval import Index
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleSection


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
        ModuleSection("scene-001", "当前", "场景 1", 1, 1, "当前线索是钥匙。"),
        ModuleSection("scene-002", "未来", "场景 2", 2, 2, "未来秘密是医生。"),
    ]))
    dispatch = make_dispatcher(session)
    result = dispatch("search_module", {"query": "医生"})
    assert "当前线索" in str(result)
    assert "未来秘密" not in str(result)
    advanced = dispatch("advance_module", {"reason": "玩家已打开门"})
    assert advanced["scene"] == "未来"
