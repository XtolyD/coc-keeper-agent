# -*- coding: utf-8 -*-
"""模组抽取（MinerU 版）：从 ParseResult 抽取模组结构化数据。

输入：`docparser.ParseResult`（MinerU 已解析的结构，含 blocks/images）。
对每个 image 块 → DeepSeek 视觉分析（地图地名/角色卡数值/插图描述）；
text 块直接复用 MinerU 文本（不消耗视觉）。再归并 NPC/地点/怪物/理智威胁。

设计：可注入 vision（默认 DeepSeek 视觉）；纯逻辑可测（注入 mock vision）。
不依赖 pymupdf（版面理解已由 MinerU 完成）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..docparser import MinerUClient
from ..docparser.result import Block, ParseResult
from ..vision import VisionClient, VisionResult
from .schema import ModuleDocument


class ModuleExtractor:
    """从 ParseResult 抽取模组结构化数据。可重复调用（每次独立、幂等）。"""

    def __init__(self, vision: Optional[VisionClient] = None):
        self.vision = vision or VisionClient()

    def extract(self, pdf_path: str, out_dir: Optional[str] = None) -> ModuleDocument:
        """解析一个模组 PDF → ModuleDocument。

        内部先走 MinerU（docparser）拿 ParseResult；再对图片块做视觉。
        """
        parser = MinerUClient()
        result = parser.parse_pdf(str(pdf_path), out_dir=out_dir)
        return self.extract_from_result(result)

    def extract_from_result(self, result: ParseResult) -> ModuleDocument:
        """从已解析的 ParseResult 抽取模组数据（可单测/复用）。"""
        # text 块直接用 MinerU 文本（不消耗视觉）；image 块用 vision
        texts = [b.text for b in result.blocks if b.type == "text" and b.text.strip()]
        image_blocks = [b for b in result.blocks if b.type == "image"]

        npcs, locations, monsters, sanity = [], [], [], []
        image_results: list[dict] = []
        for b in image_blocks:
            vr = self._recognize_image(b, result)
            if vr is None:
                continue
            image_results.append({"page_idx": b.page_idx, **vr.to_dict()})
            _merge_visual_entities(vr.data, npcs, locations, monsters, sanity)

        full_text = "\n".join(texts)
        return ModuleDocument(
            source_pdf=result.source_pdf,
            title=self._guess_title(result),
            summary=full_text[:200],
            npcs=npcs, locations=locations,
            monsters=monsters, sanity_threats=sanity,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            image_results=image_results,
            text_count=len(texts),
        )

    def _recognize_image(self, b: Block, result: ParseResult) -> Optional[VisionResult]:
        """对单个 image 块做视觉识别（地图/角色卡/插图）。"""
        img_abs = self._resolve_img_path(b, result)
        if not img_abs:
            return None
        try:
            # 先分类，再按类型精抽取
            vr = self.vision.recognize_page(img_abs)
            ct = vr.content_type
            if ct == "map":
                extra = self.vision.recognize_map(img_abs)
                vr.data.update(extra)
            elif ct == "character":
                extra = self.vision.recognize_character(img_abs)
                vr.data.update(extra)
            return vr
        except Exception:  # noqa: BLE001 —— 单图识别失败不中断整本
            return None

    @staticmethod
    def _resolve_img_path(b: Block, result: ParseResult) -> str:
        """把 image 块的 img_path 解析为绝对路径。"""
        if not b.img_path or not result.images_dir:
            return ""
        return str(Path(result.images_dir) / Path(b.img_path).name)

    @staticmethod
    def _guess_title(result: ParseResult) -> Optional[str]:
        """从 text 块猜模组名（取首个较长的标题/文本行）。"""
        for b in result.blocks:
            if b.type == "text" and b.text.strip():
                first = b.text.strip().splitlines()[0].strip()
                if 2 <= len(first) <= 30 and not first.isdigit():
                    return first
        return None


def _merge_visual_entities(data: dict, npcs, locations, monsters, sanity) -> None:
    """把视觉结果里的实体并入模组级列表（去重保序）。"""
    for key, bucket in (
        ("locations", locations), ("monsters", monsters),
        ("sanity_threats", sanity), ("npcs", npcs),
    ):
        items = data.get(key) or []
        if isinstance(items, str):
            items = [items]
        for item in items:
            if isinstance(item, str) and item and item not in bucket:
                bucket.append(item)


def extract_module(pdf_path: str, out_dir: Optional[str] = None) -> ModuleDocument:
    """便捷入口：解析单个模组 PDF。"""
    return ModuleExtractor().extract(pdf_path, out_dir)


def extract_batch(pdf_paths: list[str], out_dir: Optional[str] = None) -> list[ModuleDocument]:
    """批量解析多个模组 PDF。"""
    return [ModuleExtractor().extract(p, out_dir) for p in pdf_paths]
