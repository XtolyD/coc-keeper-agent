# -*- coding: utf-8 -*-
"""独立模组库；战役只引用模组 ID。"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .modules import KeeperModule, PDFModuleImporter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModuleRecord:
    id: str
    module: KeeperModule
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "id": self.id, "created_at": self.created_at, "module": self.module.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleRecord":
        return cls(str(data["id"]), KeeperModule.from_dict(data["module"]), str(data.get("created_at", _now())))

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.module.title, "source_name": self.module.source_name,
            "scenes": len(self.module.scenes), "actors": len(self.module.actors),
            "pages": max(scene.page_end for scene in self.module.scenes),
            "analysis_status": self.module.analysis.get("status", "needs-review"),
            "created_at": self.created_at,
        }


class ModuleStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, module_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", module_id):
            raise ValueError("模组 ID 必须是 32 位十六进制字符串")
        return self.root / f"{module_id}.json"

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def add(self, module: KeeperModule) -> ModuleRecord:
        record = ModuleRecord(uuid.uuid4().hex, module, _now())
        self._write(self._path(record.id), record.to_dict())
        return record

    def import_pdf(self, path: str | Path, *, title: str | None = None) -> ModuleRecord:
        return self.add(PDFModuleImporter().import_pdf(path, title=title))

    def get(self, module_id: str) -> ModuleRecord:
        path = self._path(module_id)
        if not path.exists():
            raise FileNotFoundError(f"模组不存在: {module_id}")
        return ModuleRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, module_id: str, module: KeeperModule) -> ModuleRecord:
        current = self.get(module_id)
        current.module = module
        self._write(self._path(module_id), current.to_dict())
        return current

    def delete(self, module_id: str) -> None:
        path = self._path(module_id)
        if not path.exists():
            raise FileNotFoundError(f"模组不存在: {module_id}")
        path.unlink()

    def list(self) -> list[ModuleRecord]:
        records: list[ModuleRecord] = []
        for path in self.root.glob("*.json"):
            try:
                records.append(ModuleRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(records, key=lambda record: record.created_at, reverse=True)
