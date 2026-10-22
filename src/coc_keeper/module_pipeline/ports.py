# -*- coding: utf-8 -*-
"""模组导入的端口定义（Protocol）与跨步骤结果。

只抽象外部能力：PDF 解析、复核、语义分析。领域模型与仓储保持为具体类型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..docparser.result import ParseResult
from ..modules import KeeperModule, ModuleSourceChunk


@dataclass
class ReviewOutcome:
    """DeepSeek 复核结果。"""

    chunks: list[ModuleSourceChunk] = field(default_factory=list)
    visual_entities: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    status: str = "complete"


class DocumentParser(Protocol):
    """PDF → MinerU ParseResult。"""

    def parse(self, pdf_path: Path, *, refresh: bool = False) -> ParseResult: ...


class ModuleReviewer(Protocol):
    """MinerU 原文 → DeepSeek 复核结果。"""

    def review(
        self,
        chunks: list[ModuleSourceChunk],
        parsed: ParseResult,
    ) -> ReviewOutcome: ...


class ModuleAnalyzer(Protocol):
    """复核后的模组 → actors/locations/scenes/story。"""

    def analyze(self, module: KeeperModule) -> KeeperModule: ...
