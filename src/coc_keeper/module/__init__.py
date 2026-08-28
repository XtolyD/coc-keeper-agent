# -*- coding: utf-8 -*-
"""模组识别（Mod 抽取）：以 MinerU ParseResult 为输入，抽取模组结构化数据。

与规则书检索（M2 `retrieval/`）完全分离。提供：
- `ModuleExtractor`：可注入 vision（默认 DeepSeek 视觉）的抽取器；
- `extract_module(pdf)`：单个模组；
- `extract_batch(pdfs)`：多个模组批量。

输入 PDF 先经 docparser（MinerU）解析；image 块再经 vision（DeepSeek 视觉）分析。
"""
from __future__ import annotations

from ..vision import VisionClient, VisionResult
from .extractor import ModuleExtractor, extract_batch, extract_module
from .schema import ModuleDocument, Page

__all__ = [
    "ModuleExtractor",
    "VisionClient",
    "VisionResult",
    "ModuleDocument",
    "Page",
    "extract_module",
    "extract_batch",
]
