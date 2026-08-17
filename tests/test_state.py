# -*- coding: utf-8 -*-
from coc_keeper.agent.state import CampaignStore, Session
from coc_keeper.character import CharacterSheet
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleSection


def test_session_multiplayer_roundtrip(tmp_path):
    session = Session(investigator=CharacterSheet(name="甲"))
    session.add_player(CharacterSheet(name="乙", hp=3, san=40))
    session.scene = "旧宅门厅"
    session.log("发现线索", clue="染血钥匙")
    session.module = ModuleRuntime(KeeperModule("旧宅", "old-house.pdf", [
        ModuleSection("scene-001", "门厅", "场景 1", 1, 2, "门厅内容"),
    ]))
    path = session.save(tmp_path / "campaign.json")
    restored = Session.load(path)
    assert set(restored.players) == {"甲", "乙"}
    assert restored.players["乙"].hp == 3
    assert restored.players["乙"].san == 40
    assert restored.scene == "旧宅门厅"
    assert restored.campaign_log[0]["details"]["clue"] == "染血钥匙"
    assert restored.module.module.title == "旧宅"


def test_campaign_store(tmp_path):
    store = CampaignStore(tmp_path / "saves")
    session_id, session = store.create(Session(investigator=CharacterSheet(name="玩家")))
    assert session_id in store.list_ids()
    assert store.load(session_id).investigator.name == "玩家"


def test_campaign_store_rejects_path_traversal(tmp_path):
    import pytest

    store = CampaignStore(tmp_path / "saves")
    with pytest.raises(ValueError):
        store.load("../outside")


def test_team_luck_check(scripted):
    session = Session(investigator=CharacterSheet(name="甲", luck=50))
    session.add_player(CharacterSheet(name="乙", luck=50))
    results = session.team_luck_check(rng=scripted(0, 3, 0, 7))
    assert results["甲"]["成功"] is True
    assert results["乙"]["成功"] is False
