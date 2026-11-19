"""协调战役回合与永久角色的保存，并恢复中断的写入。"""
from __future__ import annotations

import threading
import uuid

from .character import CharacterSheet
from .character_store import CharacterRecord, CharacterStore
from .game_store import GameRecord, GameStore
from .storage import JsonRecordRepository


class TurnStore:
    """用写前快照协调两个 JSON 记录；提交标记写入前均可恢复。"""

    def __init__(self, games: GameStore, characters: CharacterStore):
        self.games = games
        self.characters = characters
        self._lock = threading.RLock()
        self.journal = JsonRecordRepository(
            games.repository.root / ".transactions",
            id_pattern=r"[0-9a-f]{32}", decode=dict, encode=dict,
            label="回合事务", sort_key=lambda item: item["id"],
        )

    def _restore(self, transaction: dict) -> None:
        game = GameRecord.from_dict(transaction["game_before"])
        character = CharacterRecord.from_dict(transaction["character_before"])
        self.games.repository.put(game.id, game)
        self.characters.repository.put(character.id, character)

    def recover(self) -> None:
        """在服务启动和处理请求前恢复尚未提交的回合。"""
        with self._lock:
            # 直接读取每份日志，损坏日志必须阻止继续写入。
            for path in sorted(self.journal.root.glob("*.json")):
                transaction = self.journal.get(path.stem)
                if transaction["state"] == "pending":
                    self._restore(transaction)
                    self.journal.delete(path.stem)
                elif transaction["state"] == "committed":
                    self._discard_committed(path.stem)
                else:
                    raise ValueError("回合事务状态无效")

    def _discard_committed(self, transaction_id: str) -> None:
        try:
            self.journal.delete(transaction_id)
        except OSError:
            # 标记成功意味着两个记录均已保存，清理失败不能重执行行动。
            pass

    def synchronize_character(self, record: GameRecord) -> CharacterRecord:
        """每回合使用永久角色的最新数值，避免旧战役快照覆盖新状态。"""
        character = self.characters.get(record.character_id)
        sheet = CharacterSheet.from_dict(character.sheet.to_dict())
        record.session.investigator = sheet
        return character

    def commit(self, record: GameRecord, character_before: CharacterRecord) -> None:
        with self._lock:
            transaction_id = uuid.uuid4().hex
            transaction = {
                "id": transaction_id, "state": "pending",
                "game_before": self.games.get(record.id).to_dict(),
                "character_before": character_before.to_dict(),
            }
            self.journal.put(transaction_id, transaction)
            try:
                self.games.save(record)
                self.characters.save(record.character_id, record.session.investigator)
                self.journal.put(transaction_id, {**transaction, "state": "committed"})
            except Exception:
                # 如果恢复本身失败，保留日志，下次请求或重启时先恢复。
                self._restore(transaction)
                self.journal.delete(transaction_id)
                raise
            self._discard_committed(transaction_id)
