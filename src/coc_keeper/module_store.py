# -*- coding: utf-8 -*-
"""独立模组库；战役只引用模组 ID。"""
from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .modules import KeeperModule
from .storage import JsonRecordRepository


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
        self.repository = JsonRecordRepository(
            root,
            id_pattern=r"[0-9a-f]{32}",
            decode=ModuleRecord.from_dict,
            encode=lambda record: record.to_dict(),
            label="模组",
            sort_key=lambda record: record.created_at,
        )

    def _path(self, module_id: str) -> Path:
        return self.repository.path(module_id)

    def _source_path(self, module_id: str) -> Path:
        self._path(module_id)  # Validate the identifier through the shared guard.
        return self.repository.root / f"{module_id}.pdf"

    def add(self, module: KeeperModule) -> ModuleRecord:
        record = ModuleRecord(uuid.uuid4().hex, module, _now())
        return self.repository.put(record.id, record)

    def create(self, module: KeeperModule, source_pdf: str | Path | None = None) -> ModuleRecord:
        """保存已解析完成的模组；可选保留源 PDF。"""
        record = self.add(module)
        if source_pdf is None:
            return record
        destination = self._source_path(record.id)
        temporary = destination.with_suffix(".pdf.tmp")
        try:
            shutil.copyfile(Path(source_pdf), temporary)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            self._path(record.id).unlink(missing_ok=True)
            raise
        return record

    def source_pdf_path(self, module_id: str) -> Path | None:
        path = self._source_path(module_id)
        return path if path.exists() else None

    def get(self, module_id: str) -> ModuleRecord:
        return self.repository.get(module_id)

    def save(self, module_id: str, module: KeeperModule) -> ModuleRecord:
        current = self.get(module_id)
        current.module = module
        return self.repository.put(module_id, current)

    def delete(self, module_id: str) -> None:
        self.repository.delete(module_id)
        self._source_path(module_id).unlink(missing_ok=True)

    def list(self) -> list[ModuleRecord]:
        return self.repository.list()
