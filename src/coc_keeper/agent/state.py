# -*- coding: utf-8 -*-
"""会话状态：一局跑团中需要被工具读写、被持久化的可变状态。"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..character import CharacterSheet, create_character
from ..modules import ModuleRuntime
from ..rules.checks import luck_check
from ..rules.insanity import InsanityState, InsanityTracker


@dataclass
class Session:
    """一局跑团的会话状态。MVP 为单调查员；M4 扩展为多人队伍。"""
    investigator: CharacterSheet = field(default_factory=create_character)
    players: dict[str, CharacterSheet] = field(default_factory=dict)
    scene: str = ""
    campaign_log: list[dict[str, Any]] = field(default_factory=list)
    insanity: InsanityTracker = field(default_factory=InsanityTracker)
    module: ModuleRuntime | None = None
    character_id: str | None = None
    module_id: str | None = None

    def __post_init__(self) -> None:
        if not self.players:
            self.players = {self.investigator.name: self.investigator}
        else:
            self.players[self.investigator.name] = self.investigator

    def add_player(self, sheet: CharacterSheet) -> None:
        self.players[sheet.name] = sheet

    def remove_player(self, name: str) -> None:
        if name == self.investigator.name:
            raise ValueError("不能移除主调查员")
        self.players.pop(name, None)

    def get_player(self, name: str | None = None) -> CharacterSheet:
        return self.investigator if not name else self.players[name]

    def log(self, event: str, **details: Any) -> None:
        self.campaign_log.append({"event": event, "details": details})

    def team_luck_check(self, *, rng=None) -> dict[str, dict]:
        """对所有玩家分别做幸运检定，返回每名玩家的可序列化结果。"""
        return {
            name: {
                "幸运": sheet.luck,
                "检定": (result := luck_check(sheet.luck, rng=rng)).roll,
                "成功": result.success,
                "结果": result.degree_name,
            }
            for name, sheet in self.players.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigator": self.investigator.to_dict(),
            "players": {name: sheet.to_dict() for name, sheet in self.players.items()},
            "scene": self.scene,
            "campaign_log": list(self.campaign_log),
            "insanity": {
                "state": self.insanity.state.value,
                "day_total_loss": self.insanity.day_total_loss,
                "day_start_san": self.insanity.day_start_san,
                "temporary_hours": self.insanity.temporary_hours,
            },
            "module": self.module.to_dict() if self.module else None,
            "character_id": self.character_id,
            "module_id": self.module_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        investigator = CharacterSheet.from_dict(data.get("investigator", {}))
        players_data = data.get("players", {})
        players = {
            name: CharacterSheet.from_dict(sheet)
            for name, sheet in players_data.items()
        }
        tracker_data = data.get("insanity", {})
        tracker = InsanityTracker(
            state=InsanityState(tracker_data.get("state", InsanityState.STABLE.value)),
            day_total_loss=int(tracker_data.get("day_total_loss", 0)),
            day_start_san=int(tracker_data.get("day_start_san", 0)),
            temporary_hours=int(tracker_data.get("temporary_hours", 0)),
        )
        module_data = data.get("module")
        return cls(
            investigator=investigator, players=players, scene=str(data.get("scene", "")),
            campaign_log=list(data.get("campaign_log", [])), insanity=tracker,
            module=ModuleRuntime.from_dict(module_data) if module_data else None,
            character_id=data.get("character_id"), module_id=data.get("module_id"),
        )

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class CampaignStore:
    """JSON 文件型多人会话存储，M4 的最小可用持久化实现。"""
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, session: Optional[Session] = None) -> tuple[str, Session]:
        session_id = uuid.uuid4().hex
        session = session or Session()
        session.save(self.root / f"{session_id}.json")
        return session_id, session

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("会话 ID 必须是 32 位十六进制字符串")
        return self.root / f"{session_id}.json"

    def save(self, session_id: str, session: Session) -> Path:
        return session.save(self._path(session_id))

    def load(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        return Session.load(path)

    def list_ids(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))
