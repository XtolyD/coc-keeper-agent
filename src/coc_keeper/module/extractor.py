# -*- coding: utf-8 -*-
"""模组抽取编排：逐页「文本读取 + 视觉验证」双轨 → 合并为 ModuleDocument。

每页流程：
1. pdf_reader 渲染图片 + 抽文字层；
2. vision.recognize_page 识别页面类型 + 结构化数据；
3. 合并进 Page.visual；失败页标记 visual 为空但不中断整本。

模组级归并（NPC/地点/怪物/理智）由 vision 返回 + 规则辅助提炼。
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .pdf_reader import render_pages
from .schema import ModuleDocument, Page
from .vision import VisionClient


class ModuleExtractor:
    """从模组 PDF 抽取结构化数据。可重复调用（每次独立、幂等）。"""

    def __init__(self, vision: Optional[VisionClient] = None, page_dpi: int = 120):
        self.vision = vision or VisionClient()
        self.page_dpi = page_dpi

    def extract(self, pdf_path: str, out_dir: Optional[str] = None) -> ModuleDocument:
        """解析一个模组 PDF。

        返回 ModuleDocument；可选把渲染图落在 out_dir（便于复核/审计）。
        不落盘则用临时目录（用完即弃，避免生成物堆积）。
        """
        pdf_path = str(pdf_path)
        source_name = Path(pdf_path).name
        if out_dir is None:
            out_dir = tempfile.mkdtemp(prefix="mod_pages_")

        # 1. 分页：渲染图 + 文字层
        pages = render_pages(pdf_path, out_dir, dpi=self.page_dpi)

        # 2. 逐页视觉识别（失败不中断）
        for page in pages:
            if not page.image_path:
                vision = {"content_type": "error", "description": "无渲染图"}
            else:
                try:
                    vision = self.vision.recognize_page(page.image_path)
                    page.visual = vision.to_dict()
                    page.content_type = vision.content_type
                    # 按类型补充精抽取（地图/角色卡）
                    if vision.content_type == "map":
                        map_data = self.vision.recognize_map(page.image_path)
                        page.visual["locations"] = map_data.get("locations", [])
                    elif vision.content_type == "character":
                        char_data = self.vision.recognize_character(page.image_path)
                        page.visual.update(char_data)
                    continue
                except Exception as e:  # noqa: BLE001 —— 单页失败不中断整本
                    vision = {"content_type": "error", "description": f"视觉识别失败: {e}"}
            page.visual = vision
            page.content_type = vision.get("content_type", "text")

        # 3. 模组级归并
        title = _guess_title(pages)
        npcs, locations, monsters, sanity = _merge_entities(pages)
        summary = _guess_summary(pages)

        return ModuleDocument(
            source_pdf=pdf_path,
            title=title,
            pages=pages,
            summary=summary,
            npcs=npcs,
            locations=locations,
            monsters=monsters,
            sanity_threats=sanity,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
        )


def extract_module(pdf_path: str, out_dir: Optional[str] = None) -> ModuleDocument:
    """便捷入口：一次性解析单个模组 PDF。"""
    return ModuleExtractor().extract(pdf_path, out_dir)


def extract_batch(pdf_paths: list[str], out_dir: Optional[str] = None) -> list[ModuleDocument]:
    """批量解析多个模组 PDF，各自独立输出。"""
    return [ModuleExtractor().extract(p, out_dir) for p in pdf_paths]


# ---- 归并辅助（纯函数，可单测）----------------------------------------------
def _guess_title(pages: list[Page]) -> Optional[str]:
    """从视觉/文字层猜模组名：优先首页文字层首个非空行。"""
    if not pages:
        return None
    for p in pages[:3]:
        for line in p.text.splitlines():
            line = line.strip()
            if len(line) >= 2 and not line.isdigit():
                return line
    return None


def _merge_entities(pages: list[Page]) -> tuple[list, list, list, list]:
    """从各页视觉结果聚合 NPC/地点/怪物/理智威胁（去重保序）。"""
    npcs, locations, monsters, sanity = [], [], [], []
    for p in pages:
        v = p.visual or {}
        for k, bucket in (
            ("locations", locations),
            ("monsters", monsters),
            ("sanity_threats", sanity),
            ("npcs", npcs),
        ):
            for item in _as_list(v.get(k)):
                if item and item not in bucket:
                    bucket.append(item)
    return npcs, locations, monsters, sanity


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def _guess_summary(pages: list[Page]) -> str:
    """取第一个有 description 的页作为剧情简述起点。"""
    for p in pages:
        v = p.visual or {}
        desc = v.get("description")
        if desc:
            return desc
    return ""
