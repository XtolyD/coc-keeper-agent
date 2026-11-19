from copy import deepcopy

import pytest

from coc_keeper.agent.state import Session
from coc_keeper.character import CharacterSheet
from coc_keeper.character_store import CharacterStore
from coc_keeper.game_store import GameStore
from coc_keeper.turn_store import TurnStore


def make_stores(tmp_path):
    characters, games = CharacterStore(tmp_path / "characters"), GameStore(tmp_path / "games")
    character = characters.create(CharacterSheet(name="调查员", hp=10))
    sheet = CharacterSheet.from_dict(character.sheet.to_dict())
    game = games.create("战役", character.id, "a" * 32, Session(investigator=sheet))
    turns = TurnStore(games, characters)
    return characters, games, character, game, turns


def test_pending_journal_recovers_after_interrupted_write(tmp_path):
    characters, games, character, game, turns = make_stores(tmp_path)
    snapshot = game.to_dict()
    transaction_id = "b" * 32
    turns.journal.put(transaction_id, {
        "id": transaction_id, "state": "pending",
        "game_before": snapshot, "character_before": character.to_dict(),
    })
    game.session.investigator.hp = 7
    games.save(game)
    characters.save(character.id, game.session.investigator)
    restarted = TurnStore(games, characters)
    restarted.recover()
    assert games.get(game.id).to_dict() == snapshot
    assert characters.get(character.id).sheet.hp == 10
    assert list(turns.journal.root.glob("*.json")) == []


def test_rollback_failure_keeps_journal_for_recovery(tmp_path, monkeypatch):
    characters, games, character, game, turns = make_stores(tmp_path)
    snapshot = deepcopy(game.to_dict())
    original_put = characters.repository.put
    game.session.investigator.hp = 7

    def fail(*args, **kwargs):
        raise OSError("injected write and rollback failure")

    monkeypatch.setattr(characters.repository, "put", fail)
    with pytest.raises(OSError):
        turns.commit(game, character)
    assert len(list(turns.journal.root.glob("*.json"))) == 1
    monkeypatch.setattr(characters.repository, "put", original_put)
    turns.recover()
    assert games.get(game.id).to_dict() == snapshot
    assert characters.get(character.id).sheet.hp == 10


def test_committed_cleanup_failure_does_not_replay_or_undo_turn(tmp_path, monkeypatch):
    characters, games, character, game, turns = make_stores(tmp_path)
    game.session.investigator.hp = 7
    original_delete = turns.journal.delete

    def fail(*args, **kwargs):
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(turns.journal, "delete", fail)
    turns.commit(game, character)
    assert characters.get(character.id).sheet.hp == 7
    latest = characters.get(character.id)
    latest.sheet.hp = 6
    characters.save(character.id, latest.sheet)
    turns.recover()
    assert characters.get(character.id).sheet.hp == 6
    monkeypatch.setattr(turns.journal, "delete", original_delete)
    turns.recover()
    assert list(turns.journal.root.glob("*.json")) == []


def test_commit_marker_failure_restores_both_snapshots(tmp_path, monkeypatch):
    characters, games, character, game, turns = make_stores(tmp_path)
    snapshot = deepcopy(game.to_dict())
    game.session.investigator.hp = 7
    original_put = turns.journal.put

    def fail_marker(record_id, value):
        if value["state"] == "committed":
            raise OSError("injected commit marker failure")
        return original_put(record_id, value)

    monkeypatch.setattr(turns.journal, "put", fail_marker)
    with pytest.raises(OSError):
        turns.commit(game, character)
    assert games.get(game.id).to_dict() == snapshot
    assert characters.get(character.id).sheet.hp == 10
    assert list(turns.journal.root.glob("*.json")) == []
