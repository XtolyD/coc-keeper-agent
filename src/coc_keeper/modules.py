# -*- coding: utf-8 -*-
"""PDF 模组导入、当前场景上下文与防剧透运行时。

完整模组只保存在 Keeper 侧。Agent 每次只能获得当前场景的文本；未来场景既不进入
系统提示，也不通过工具返回。输出门禁还会拦截未来场景的显式秘密和长原文片段。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from .rules.retrieval import RuleIndex


@dataclass
class ModuleSection:
    id: str
    keeper_title: str
    public_title: str
    page_start: int
    page_end: int
    text: str
    objectives: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleSection":
        return cls(
            id=str(data["id"]), keeper_title=str(data.get("keeper_title", data["id"])),
            public_title=str(data.get("public_title", "当前场景")),
            page_start=int(data.get("page_start", 0)), page_end=int(data.get("page_end", 0)),
            text=str(data.get("text", "")), objectives=list(data.get("objectives", [])),
            secrets=list(data.get("secrets", [])),
        )


@dataclass
class KeeperModule:
    title: str
    source_name: str
    sections: list[ModuleSection]
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version, "title": self.title, "source_name": self.source_name,
            "sections": [asdict(section) for section in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeeperModule":
        sections = [ModuleSection.from_dict(item) for item in data.get("sections", [])]
        if not sections:
            raise ValueError("模组至少需要一个场景")
        return cls(
            title=str(data.get("title", "未命名模组")),
            source_name=str(data.get("source_name", "")), sections=sections,
            version=int(data.get("version", 1)),
        )

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "KeeperModule":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


class PDFModuleImporter:
    """把有目录或无目录的长短 PDF 转为可编辑 JSON 模组。"""

    def __init__(self, *, max_pages: int = 1000, max_pages_per_section: int = 8, max_page_chars: int = 30000):
        self.max_pages = max(1, int(max_pages))
        self.max_pages_per_section = max(1, int(max_pages_per_section))
        self.max_page_chars = max(1000, int(max_page_chars))

    def import_pdf(self, path: str | Path, *, title: str | None = None) -> KeeperModule:
        source = Path(path)
        if source.suffix.lower() != ".pdf":
            raise ValueError("模组文件必须是 PDF")
        if not source.exists():
            raise FileNotFoundError(source)
        with pymupdf.open(source) as doc:
            if doc.page_count < 1:
                raise ValueError("PDF 没有页面")
            if doc.page_count > self.max_pages:
                raise ValueError(f"PDF 页数 {doc.page_count} 超过上限 {self.max_pages}")
            page_text = [doc.load_page(i).get_text("text")[: self.max_page_chars].strip() for i in range(doc.page_count)]
            if sum(len(text) for text in page_text) < 20:
                raise ValueError("PDF 未提取到足够文本；扫描版 PDF 请先进行 OCR")
            ranges = self._ranges(doc, page_text)

        sections: list[ModuleSection] = []
        for index, (keeper_title, start, end) in enumerate(ranges, 1):
            text = "\n".join(
                f"===== 第 {page + 1} 页 =====\n{page_text[page]}"
                for page in range(start - 1, end) if page_text[page]
            ).strip()
            if not text:
                continue
            sections.append(ModuleSection(
                id=f"scene-{index:03d}", keeper_title=keeper_title,
                public_title=f"场景 {index}", page_start=start, page_end=end, text=text,
            ))
        if not sections:
            raise ValueError("PDF 中没有可用的文本场景")
        inferred_title = title or self._infer_title(page_text, source.stem)
        return KeeperModule(inferred_title, source.name, sections)

    def _ranges(self, doc: pymupdf.Document, page_text: list[str]) -> list[tuple[str, int, int]]:
        toc = [entry for entry in doc.get_toc(simple=True) if 1 <= int(entry[2]) <= doc.page_count]
        if toc:
            base_level = min(int(entry[0]) for entry in toc)
            entries = [(str(title).strip() or "未命名章节", int(page)) for level, title, page in toc if int(level) == base_level]
        else:
            entries = []
        if not entries:
            entries = [("开场", 1)]
        if entries[0][1] > 1:
            entries.insert(0, ("前置资料", 1))

        ranges: list[tuple[str, int, int]] = []
        for index, (heading, start) in enumerate(entries):
            end = entries[index + 1][1] - 1 if index + 1 < len(entries) else len(page_text)
            part = 1
            cursor = start
            while cursor <= end:
                part_end = min(end, cursor + self.max_pages_per_section - 1)
                suffix = f"（{part}）" if end - start + 1 > self.max_pages_per_section else ""
                ranges.append((heading + suffix, cursor, part_end))
                cursor = part_end + 1
                part += 1
        return ranges

    @staticmethod
    def _infer_title(page_text: list[str], fallback: str) -> str:
        for line in page_text[0].splitlines():
            candidate = line.strip()
            if 2 <= len(candidate) <= 80:
                return candidate
        return fallback


@dataclass
class ModuleRuntime:
    module: KeeperModule
    current_index: int = 0
    completed: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)

    @property
    def current(self) -> ModuleSection:
        return self.module.sections[self.current_index]

    @property
    def finished(self) -> bool:
        return self.current_index >= len(self.module.sections) - 1 and self.current.id in self.completed

    def status(self, *, player_safe: bool = True) -> dict[str, Any]:
        result = {
            "module": self.module.title,
            "scene": self.current.public_title if player_safe else self.current.keeper_title,
            "progress": f"{self.current_index + 1}/{len(self.module.sections)}",
            "finished": self.finished,
        }
        if not player_safe:
            result.update({"pages": [self.current.page_start, self.current.page_end], "objectives": self.current.objectives})
        return result

    def keeper_context(self, query: str = "", *, limit: int = 3, max_chars: int = 8000) -> dict[str, Any]:
        """只返回当前场景内容，绝不检索未来场景。"""
        section = self.current
        chunks = RuleIndex.from_text(section.text).search(query, limit=limit) if query.strip() else []
        excerpts = [
            {"page": hit.page, "text": hit.text[:2000], "score": round(hit.score, 4)}
            for hit in chunks
        ]
        if not excerpts:
            excerpts = [{"page": section.page_start, "text": section.text[:max_chars], "score": 0.0}]
        return {
            "module": self.module.title,
            "current_scene": section.keeper_title,
            "public_scene": section.public_title,
            "pages": [section.page_start, section.page_end],
            "objectives": list(section.objectives),
            "excerpts": excerpts,
            "discipline": "只能使用当前场景和已发生事件；不得提及未来场景、秘密或完整剧情。",
        }

    def advance(self, reason: str, completed_objectives: list[str] | None = None) -> dict[str, Any]:
        current = self.current
        completed_objectives = completed_objectives or []
        missing = [objective for objective in current.objectives if objective not in completed_objectives]
        if missing:
            raise ValueError("当前场景目标尚未完成: " + "、".join(missing))
        if not str(reason).strip():
            raise ValueError("推进场景必须说明已发生的游戏内原因")
        if current.id not in self.completed:
            self.completed.append(current.id)
        self.history.append({"scene": current.id, "reason": str(reason).strip()})
        if self.current_index < len(self.module.sections) - 1:
            self.current_index += 1
        return self.status(player_safe=False)

    def detects_spoiler(self, output: str) -> bool:
        """检查显式 secrets 和未来原文长片段；用于最终输出门禁。"""
        normalized = self._normalize(output)
        if not normalized:
            return False
        for section in self.module.sections[self.current_index + 1:]:
            if any(self._normalize(secret) in normalized for secret in section.secrets if self._normalize(secret)):
                return True
            for sentence in re.split(r"[。！？!?\n]", section.text):
                future = self._normalize(sentence)
                if len(future) < 16:
                    continue
                for start in range(0, len(future) - 15, 8):
                    if future[start:start + 16] in normalized:
                        return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\W+", "", str(text), flags=re.UNICODE).lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module.to_dict(), "current_index": self.current_index,
            "completed": list(self.completed), "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleRuntime":
        runtime = cls(
            KeeperModule.from_dict(data["module"]), int(data.get("current_index", 0)),
            list(data.get("completed", [])), list(data.get("history", [])),
        )
        runtime.current_index = max(0, min(runtime.current_index, len(runtime.module.sections) - 1))
        return runtime


def load_module(path: str | Path, *, title: str | None = None) -> ModuleRuntime:
    source = Path(path)
    module = PDFModuleImporter().import_pdf(source, title=title) if source.suffix.lower() == ".pdf" else KeeperModule.load(source)
    return ModuleRuntime(module)
