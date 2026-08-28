# -*- coding: utf-8 -*-
"""语义分块器：MinerU content_list → 语义块（RAG 可检索）。

与规则书/模组书解耦，只从 content_list 分块。核心：
- `chunk_content_list(blocks)` → list[Chunk]
- `Chunk`：语义块数据类（字段对齐 rules_chunks.json）
- `is_noise` / `is_title`：噪声与标题判定
"""
from __future__ import annotations

from .chunker import (
    Chunk, chunk_content_list, is_noise, is_title, rulebook_type_fn, _default_type_fn,
)

__all__ = [
    "Chunk", "chunk_content_list", "is_noise", "is_title",
    "rulebook_type_fn", "_default_type_fn",
]
