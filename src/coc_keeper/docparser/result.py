# -*- coding: utf-8 -*-
"""MinerU 解析结果的数据模型与纯函数解析。

`content_list.json`（MinerU 产出）→ `ParseResult` / `Block`。
纯逻辑、可单测：解析 content_list 的 JSON 到块列表不依赖网络。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Block:
    """MinerU content_list 中的一个内容块。"""
    type: str                    # text/image/table/header/page_number
    text: str                    # 文本（image 类为空串）
    text_level: str              # 标题层级（""=正文；"2"=二级标题）
    page_idx: int                # 页号（0 起）
    bbox: list[float] = field(default_factory=list)  # [x0,y0,x1,y1]
    img_path: str = ""           # 图片相对路径（type=image 时如 images/xxx.jpg）
    table_body: str = ""         # 表格内容（type=table 时，MinerU 的 table_body/HTML）

    def to_dict(self) -> dict:
        return {
            "type": self.type, "text": self.text,
            "text_level": self.text_level, "page_idx": self.page_idx,
            "bbox": self.bbox, "img_path": self.img_path, "table_body": self.table_body,
        }

    @property
    def is_title(self) -> bool:
        """是否为标题块（text_level 非空）。"""
        return self.type == "text" and bool(self.text_level)


@dataclass
class ParseResult:
    """一次 PDF 解析的产物。"""
    source_pdf: str              # 原 PDF 名（含路径）
    blocks: list[Block] = field(default_factory=list)  # 有序块（页序+阅读序）
    markdown: str = ""           # full.md 全文
    images_dir: str = ""         # 图片本地目录（images/）
    content_list_path: str = ""  # 原始 content_list.json 路径
    parsed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "source_pdf": self.source_pdf,
            "blocks": [b.to_dict() for b in self.blocks],
            "markdown": self.markdown,
            "images_dir": self.images_dir,
            "content_list_path": self.content_list_path,
            "parsed_at": self.parsed_at,
        }


# ---- 纯函数：content_list 解析 -------------------------------------------------
def parse_content_list(data: list[dict]) -> list[Block]:
    """把 MinerU 的 content_list JSON（列表）转成 Block 列表。

    容错：缺失字段给默认；不合法条目跳过。返回保持原顺序（页序+阅读序）。
    """
    blocks: list[Block] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # 无 type 的条目无意义（判别字段缺失），跳过
        btype = str(item.get("type", "") or "")
        if not btype:
            continue
        text = str(item.get("text", "")) if btype != "image" else ""
        # page_idx/bbox 可能是字符串或数字
        try:
            page_idx = int(str(item.get("page_idx", "0")).strip() or "0")
        except (ValueError, TypeError):
            page_idx = 0
        bbox = _parse_bbox(item.get("bbox"))
        blocks.append(Block(
            type=btype,
            text=text,
            text_level=str(item.get("text_level", "") or ""),
            page_idx=page_idx,
            bbox=bbox,
            img_path=str(item.get("img_path", "") or ""),
            table_body=str(item.get("table_body", "") or item.get("table_caption", "") or ""),
        ))
    return blocks


def _parse_bbox(value) -> list[float]:
    """把 bbox 解析成 [x0,y0,x1,y1]；缺失/非法给空列表。"""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return []
    out = []
    for v in value:
        try:
            out.append(float(v))
        except (ValueError, TypeError):
            return []
    return out


def is_done_state(state: str) -> bool:
    """判断解析状态是否为完成。"""
    return state == "done"


def is_failed_state(state: str) -> bool:
    return state == "failed"
