# -*- coding: utf-8 -*-
"""模组导入流水线编排。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..modules import KeeperModule
from .assembler import ModuleAssembler
from .ingest import build_source_chunks
from .ports import DocumentParser, ModuleAnalyzer, ModuleReviewer

Progress = Callable[[str], None]


@dataclass
class ModuleImportRequest:
    pdf_path: Path
    title: str | None = None
    source_name: str | None = None
    reparse: bool = False


class ModuleImportPipeline:
    """MinerU 解析 → DeepSeek 复核 → 结构分析。

    三个能力通过 Protocol 注入，便于替换供应商与离线测试。
    """

    def __init__(
        self,
        parser: DocumentParser,
        reviewer: ModuleReviewer | None = None,
        analyzer: ModuleAnalyzer | None = None,
        assembler: ModuleAssembler | None = None,
        *,
        max_pages_per_section: int = 2,
    ):
        self.parser = parser
        self.reviewer = reviewer
        self.analyzer = analyzer
        self.assembler = assembler or ModuleAssembler()
        self.max_pages_per_section = max_pages_per_section

    def run(
        self,
        request: ModuleImportRequest,
        *,
        progress: Progress | None = None,
    ) -> KeeperModule:
        report = progress or (lambda _stage: None)
        report("MinerU 解析 PDF")
        parsed = self.parser.parse(Path(request.pdf_path), refresh=request.reparse)
        report("切分原文片段")
        chunks = build_source_chunks(parsed, max_pages_per_section=self.max_pages_per_section)
        review = None
        if self.reviewer is not None:
            report("DeepSeek 复核")
            review = self.reviewer.review(chunks, parsed)
        report("组装模组结构")
        module = self.assembler.build(parsed, chunks, review, title=request.title)
        if request.source_name:
            module.source_name = request.source_name
        if self.analyzer is not None:
            report("语义结构分析")
            module = self.analyzer.analyze(module)
        report("完成")
        return module
