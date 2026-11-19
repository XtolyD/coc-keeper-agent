# -*- coding: utf-8 -*-
from coc_keeper.agent.state import CampaignStore, Session
from coc_keeper.character import CharacterSheet
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleScene


def test_session_roundtrip(tmp_path):
    session = Session(investigator=CharacterSheet(name="调查员", hp=3, san=40))
    session.scene = "旧宅门厅"
    session.log("发现线索", clue="染血钥匙")
    session.module = ModuleRuntime(KeeperModule("旧宅", "old-house.pdf", [
        ModuleScene("scene-001", "门厅", "场景 1", 1, 2, "门厅内容"),
    ]))
    path = session.save(tmp_path / "campaign.json")
    restored = Session.load(path)
    assert restored.investigator.name == "调查员"
    assert restored.investigator.hp == 3
    assert restored.investigator.san == 40
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


def test_session_save_schema():
    assert set(Session().to_dict()) == {
        "investigator", "scene", "campaign_log", "insanity", "module", "character_id", "module_id",
    }
