# -*- coding: utf-8 -*-
"""模组结构数据（纯 dataclass，无副作用）。

定义从模组 PDF 抽取出的结构化数据：页面级（文字层 + 视觉结果）与模组级
（剧情实体归并）。不依赖 pymupdf / LLM，便于单测与序列化。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Page:
    """模组 PDF 的单页。

    - text：文字层内容（pymupdf `get_text`，可为空）。
    - image_path：该页渲染出的 PNG（供视觉/审计复用）。
    - visual：视觉识别结果（dict，含 content_type + 结构化字段）。
    - content_type：页面类型，由视觉分类：text/map/character/illustration/table。
    """
    index: int
    text: str = ""
    image_path: str = ""
    visual: Optional[dict] = None
    content_type: str = "text"

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "image_path": self.image_path,
            "visual": self.visual,
            "content_type": self.content_type,
        }


@dataclass
class ModuleDocument:
    """一个模组的整体抽取结果。"""
    source_pdf: str                                   # 原 PDF 文件名（含路径）
    title: Optional[str] = None                       # 模组名
    pages: list[Page] = field(default_factory=list)
    summary: str = ""                                 # 剧情一句话总览
    npcs: list[str] = field(default_factory=list)     # 提取到的 NPC 名
    locations: list[str] = field(default_factory=list) # 地点名
    monsters: list[str] = field(default_factory=list)  # 怪物/生物
    sanity_threats: list[str] = field(default_factory=list)  # 理智威胁点
    extracted_at: str = ""                            # ISO 时间戳

    def to_dict(self) -> dict:
        return {
            "source_pdf": self.source_pdf,
            "title": self.title,
            "pages": [p.to_dict() for p in self.pages],
            "summary": self.summary,
            "npcs": self.npcs,
            "locations": self.locations,
            "monsters": self.monsters,
            "sanity_threats": self.sanity_threats,
            "extracted_at": self.extracted_at,
        }
