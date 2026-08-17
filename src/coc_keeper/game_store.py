# -*- coding: utf-8 -*-
"""持久战役记录：角色与模组独立引用，完整对话长期保存。"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent.state import Session
from .rules.retrieval import RuleChunk, RuleIndex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TranscriptEntry:
    role: str
    content: str
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptEntry":
        return cls(str(data["role"]), str(data["content"]), str(data.get("created_at", _now())))


@dataclass
class GameRecord:
    id: str
    title: str
    character_id: str
    module_id: str
    session: Session
    transcript: list[TranscriptEntry] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1, "id": self.id, "title": self.title,
            "character_id": self.character_id, "module_id": self.module_id,
            "session": self.session.to_dict(),
            "transcript": [entry.__dict__ for entry in self.transcript],
            "memory": self.memory, "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameRecord":
        return cls(
            id=str(data["id"]), title=str(data.get("title", "未命名战役")),
            character_id=str(data["character_id"]), module_id=str(data["module_id"]),
            session=Session.from_dict(data["session"]),
            transcript=[TranscriptEntry.from_dict(item) for item in data.get("transcript", [])],
            memory=list(data.get("memory", [])), created_at=str(data.get("created_at", _now())),
            updated_at=str(data.get("updated_at", _now())),
        )

    def relevant_history(self, query: str, *, limit: int = 6) -> list[str]:
        if not query.strip() or not self.transcript:
            return []
        chunks = [
            RuleChunk(index + 1, f"{entry.role}: {entry.content}")
            for index, entry in enumerate(self.transcript[:-8])
        ]
        return [hit.text for hit in RuleIndex(chunks).search(query, limit=limit)]


class GameStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, game_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", game_id):
            raise ValueError("战役 ID 必须是 32 位十六进制字符串")
        return self.root / f"{game_id}.json"

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def create(self, title: str, character_id: str, module_id: str, session: Session) -> GameRecord:
        record = GameRecord(uuid.uuid4().hex, title.strip() or "未命名战役", character_id, module_id, session)
        self.save(record)
        return record

    def save(self, record: GameRecord) -> GameRecord:
        record.updated_at = _now()
        self._write(self._path(record.id), record.to_dict())
        return record

    def get(self, game_id: str) -> GameRecord:
        path = self._path(game_id)
        if not path.exists():
            raise FileNotFoundError(f"战役不存在: {game_id}")
        return GameRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[GameRecord]:
        records: list[GameRecord] = []
        for path in self.root.glob("*.json"):
            try:
                records.append(GameRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(records, key=lambda record: record.updated_at, reverse=True)
