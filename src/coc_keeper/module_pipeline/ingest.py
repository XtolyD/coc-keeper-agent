# -*- coding: utf-8 -*-
"""MinerU content_list → 可追溯 source chunks（纯函数）。"""
from __future__ import annotations

from ..docparser.result import Block, ParseResult
from ..modules import ModuleSourceChunk

_NOISE_TYPES = {"header", "page_footnote", "page_number", "footer"}


def _block_text(block: Block) -> str:
    text = (block.text or "").strip()
    if block.type == "table" and block.table_body.strip():
        table = block.table_body.strip()
        return f"{text}\n{table}".strip() if text else table
    return text


def build_source_chunks(
    parsed: ParseResult,
    *,
    max_pages_per_section: int = 2,
) -> list[ModuleSourceChunk]:
    """按标题层级与页数切分 MinerU 块，保留原文与图片引用。

    规则：
    - 跳过页眉/页码等噪声块；
    - 标题块开启新片段（heading = 标题）；
    - 同一片段最多覆盖 ``max_pages_per_section`` 页，超出则续切；
    - table 块把 table_body 并入正文；image 块记录 img_path。
    """
    max_pages = max(1, int(max_pages_per_section))
    chunks: list[ModuleSourceChunk] = []
    current_heading = "正文"
    current_start: int | None = None
    current_end: int | None = None
    current_blocks: list[str] = []
    current_images: list[str] = []

    def flush() -> None:
        nonlocal current_start, current_end, current_blocks, current_images
        if current_start is None or not current_blocks:
            current_start = current_end = None
            current_blocks = []
            current_images = []
            return
        body = "\n".join(current_blocks).strip()
        if body:
            chunks.append(ModuleSourceChunk(
                id=f"source-{len(chunks) + 1:03d}",
                heading=current_heading,
                page_start=current_start,
                page_end=current_end or current_start,
                text=body,
                raw_text=body,
                extraction_method="mineru",
                image_paths=list(dict.fromkeys(current_images)),
            ))
        current_start = current_end = None
        current_blocks = []
        current_images = []

    for block in parsed.blocks:
        if block.type in _NOISE_TYPES:
            continue
        page = int(block.page_idx) + 1
        text = _block_text(block)
        if block.type == "image":
            if block.img_path:
                current_images.append(block.img_path)
            if current_start is None:
                current_start = current_end = page
            continue
        if not text:
            continue
        if block.is_title:
            flush()
            current_heading = text
            current_start = current_end = page
            current_blocks = [text]
            continue
        if current_start is None:
            current_start = current_end = page
        elif page > (current_end or current_start) and page - current_start + 1 > max_pages:
            heading = current_heading
            flush()
            current_heading = heading
            current_start = current_end = page
        else:
            current_end = max(current_end or page, page)
        current_blocks.append(text)

    flush()
    return chunks


def source_page_texts(parsed: ParseResult) -> list[str]:
    """按页拼接 MinerU 文本（含表格），供本地属性块抽取。"""
    pages: dict[int, list[str]] = {}
    for block in parsed.blocks:
        if block.type in _NOISE_TYPES:
            continue
        text = _block_text(block)
        if text:
            pages.setdefault(int(block.page_idx) + 1, []).append(text)
    if not pages:
        return []
    return ["\n".join(pages.get(page, [])) for page in range(1, max(pages) + 1)]
