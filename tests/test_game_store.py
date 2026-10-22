# -*- coding: utf-8 -*-
from coc_keeper.agent.state import Session
from coc_keeper.character import CharacterSheet
from coc_keeper.game_store import GameStore, TranscriptEntry
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleScene


def test_game_references_character_and_module_independently(tmp_path):
    session = Session(
        investigator=CharacterSheet(name="林恩"),
        module=ModuleRuntime(KeeperModule("旧宅", "old.pdf", [
            ModuleScene("scene-001", "门厅", "场景 1", 1, 1, "门厅里有一面镜子。"),
        ])),
        character_id="a" * 32,
        module_id="b" * 32,
    )
    store = GameStore(tmp_path / "games")
    record = store.create("旧宅调查", session.character_id, session.module_id, session)
    loaded = store.get(record.id)
    assert loaded.character_id == "a" * 32
    assert loaded.module_id == "b" * 32
    assert loaded.session.investigator.name == "林恩"
    assert loaded.session.module.module.title == "旧宅"


def test_full_transcript_persists_and_old_turns_are_retrievable(tmp_path):
    session = Session(character_id="a" * 32, module_id="b" * 32)
    store = GameStore(tmp_path / "games")
    record = store.create("长战役", session.character_id, session.module_id, session)
    record.transcript = [TranscriptEntry("user", f"第{i}回合调查钟楼") for i in range(12)]
    store.save(record)
    loaded = store.get(record.id)
    assert len(loaded.transcript) == 12
    assert loaded.relevant_history("钟楼")


def test_game_can_be_deleted_without_touching_references(tmp_path):
    store = GameStore(tmp_path / "games")
    session = Session(character_id="a" * 32, module_id="b" * 32)
    record = store.create("待删除战役", session.character_id, session.module_id, session)
    store.delete(record.id)
    assert store.list() == []
