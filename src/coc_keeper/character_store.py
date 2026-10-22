# -*- coding: utf-8 -*-
"""与模组无关的永久角色卡存储。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import JsonRecordRepository

from .character import (
    CharacterSheet, base_skill_values, interest_points_spent,
    occupation_points_spent, skill_points_spent,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CharacterRecord:
    id: str
    sheet: CharacterSheet
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        occupation_budget = self.sheet.attributes.EDU * 4
        interest_budget = self.sheet.attributes.INT * 2
        if self.sheet.occupation_id is not None:
            from .occupations import get_occupation, occupation_point_budget
            occupation_budget = occupation_point_budget(
                self.sheet.attributes, get_occupation(self.sheet.occupation_id),
            )
        return {
            "version": 1,
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "permanent": True,
            "skill_budget": occupation_budget + interest_budget,
            "skill_points_spent": skill_points_spent(self.sheet),
            "occupation_point_budget": occupation_budget,
            "occupation_points_spent": occupation_points_spent(self.sheet),
            "interest_point_budget": interest_budget,
            "interest_points_spent": interest_points_spent(self.sheet),
            "base_skills": base_skill_values(self.sheet.attributes),
            "sheet": self.sheet.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterRecord":
        return cls(
            id=str(data["id"]), sheet=CharacterSheet.from_dict(data["sheet"]),
            created_at=str(data.get("created_at", _now())),
            updated_at=str(data.get("updated_at", _now())),
        )


class CharacterStore:
    def __init__(self, root: str | Path):
        self.repository = JsonRecordRepository(
            root,
            id_pattern=r"[0-9a-f]{32}",
            decode=CharacterRecord.from_dict,
            encode=lambda record: record.to_dict(),
            label="角色卡",
            sort_key=lambda record: record.updated_at,
        )

    def create(self, sheet: CharacterSheet) -> CharacterRecord:
        now = _now()
        record = CharacterRecord(uuid.uuid4().hex, sheet, now, now)
        return self.repository.put(record.id, record)

    def get(self, record_id: str) -> CharacterRecord:
        return self.repository.get(record_id)

    def save(self, record_id: str, sheet: CharacterSheet) -> CharacterRecord:
        current = self.get(record_id)
        current.sheet = sheet
        current.updated_at = _now()
        return self.repository.put(record_id, current)

    def delete(self, record_id: str) -> None:
        self.repository.delete(record_id)

    def list(self) -> list[CharacterRecord]:
        return self.repository.list()
