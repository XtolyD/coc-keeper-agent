# -*- coding: utf-8 -*-
"""文档解析（DocParser · MinerU）：PDF → 结构化内容（content_list + full.md + 图片）。

与 `retrieval/`（RAG 检索）、`vision/`（图片分析）解耦。只做「文档→结构化」。
- `MinerUClient.parse_pdf(path)` → ParseResult（blocks / markdown / images_dir）
- `Block` / `ParseResult`：结构化数据类
- `parse_content_list(data)`：纯函数解析 content_list JSON
"""
from __future__ import annotations

from .client import DocParserError, MinerUClient
from .result import Block, ParseResult, is_done_state, is_failed_state, parse_content_list

__all__ = [
    "MinerUClient",
    "DocParserError",
    "Block",
    "ParseResult",
    "parse_content_list",
    "is_done_state",
    "is_failed_state",
]
