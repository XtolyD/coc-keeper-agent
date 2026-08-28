# -*- coding: utf-8 -*-
"""PDF 逐页读取：渲染成图片 + 抽取文字层。

用 pymupdf(fitz) 处理模组 PDF。对每一页：
- `render_page(pdf, i, out_dir)`：渲染成 PNG（供视觉识别）；
- `extract_text(pdf, i)`：抽取文字层。

纯逻辑 + pyframeworks 依赖集中在读取层；`schema.Page` 不依赖本模块。
"""
from __future__ import annotations

import os
from pathlib import Path

import fitz  # pymupdf

from .schema import Page

# 渲染 DPI：控制图片分辨率。120 够视觉识别且不至于过大。
RENDER_DPI = 120


def render_pages(pdf_path: str, out_dir: str, dpi: int = RENDER_DPI) -> list[Page]:
    """把 PDF 逐页渲染为 PNG 并抽取文字层。

    返回与页序一致的 `Page` 列表（index 从 0 起）。
    单页失败不中断：失败页仅保存 index（无图片/文字），后续仍可尝试视觉。
    """
    doc = fitz.open(pdf_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages: list[Page] = []
    for i in range(doc.page_count):
        text = _extract_text(doc, i)
        image_path = _render_image(doc, i, out, dpi)
        pages.append(Page(index=i, text=text, image_path=image_path))
    doc.close()
    return pages


def _extract_text(doc: fitz.Document, index: int) -> str:
    """抽取第 index 页文字层。失败返回空串（不中断整本）。"""
    try:
        return doc[index].get_text().strip()
    except Exception:  # noqa: BLE001 —— 单页失败不影响整体
        return ""


def _render_image(doc: fitz.Document, index: int, out_dir: Path, dpi: int = RENDER_DPI) -> str:
    """把第 index 页渲染成 PNG，返回路径。失败返回空串。"""
    try:
        pix = doc[index].get_pixmap(dpi=dpi)
        path = out_dir / f"p{index:04d}.png"
        pix.save(str(path))
        return str(path)
    except Exception:  # noqa: BLE001
        return ""
