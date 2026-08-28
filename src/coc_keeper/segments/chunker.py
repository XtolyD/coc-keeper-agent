# -*- coding: utf-8 -*-
"""语义分块器：MinerU content_list → 语义块（RAG 可检索）。

输入：`docparser.Block` 列表（含 type/text/text_level/page_idx/bbox）。
输出：语义块字典列表，字段对齐 rules_chunks.json：
    {type, name, title, text, page, start_page, end_page, path, order, lines}

分块信号（来自 MinerU，比几何启发式可靠）：
- `text_level` 非空 = 标题 → 新块边界；标题层级可重建章节 path。
- `type=table/image` → 独立块；`header/footnote/page_number` = 噪声，跳过。
- 正文 text 块累积进当前块；`page_idx` 记页号（跨页块取起止页）。

纯函数、可单测。与规则书/模组书解耦：只从 content_list 分块，不关心章节来源。
注：本模块与旧 `chunker.py`（几何启发式分块）无关，是 MinerU 管道的新分块器。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..docparser.result import Block

# 噪声块类型（页眉/脚注/页码，不参与内容/检索）
_NOISE_TYPES = {"header", "page_footnote", "page_number"}

# 特殊块类型（独立成块，不进正文累积）
_SPECIAL_TYPES = {"table", "image"}


@dataclass
class Chunk:
    """一个可检索的语义块。"""
    type: str                 # rule/skill/spell/combat/monster/tome/table/glossary/image
    name: str                 # 块标题（正文块可为空）
    title: str                # 原始标题
    text: str                 # 正文（含 name 首行）
    page: int                 # 起始页（1 起）
    start_page: int
    end_page: int
    path: str = ""            # 章节路径（由标题栈重建）
    order: int = 0
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": self.type, "name": self.name, "title": self.title,
            "text": self.text, "page": self.page,
            "start_page": self.start_page, "end_page": self.end_page,
            "path": self.path, "order": self.order, "lines": list(self.lines),
        }


def is_noise(block: Block) -> bool:
    """是否为噪声块（页眉/脚注/页码）。"""
    return block.type in _NOISE_TYPES


def is_title(block: Block) -> bool:
    """是否为标题块（text + text_level 非空）。"""
    return block.type == "text" and bool(block.text_level)


def _title_level(block: Block) -> int:
    """标题层级（text_level → int；非标题给 0）。"""
    try:
        return int(block.text_level) if block.text_level else 0
    except (ValueError, TypeError):
        return 0


TypeFn = Callable[[str, str], str]


def _default_type_fn(path: str, name: str) -> str:
    """通用类型：默认全部归 rule（table/image 由块类型单独决定）。

    规则书/模组书各自可注入更细的类型判定（如规则书按章节关键词定 skill/monster）。
    """
    return "rule"


def rulebook_type_fn(path: str, name: str) -> str:
    """规则书类型判定：按章节路径关键词定 skill/spell/monster/tome 等。

    与 build_chunks._section_type 对齐，供规则书管道注入。
    """
    if "技能" in path:
        return "skill"
    if "法术" in path:
        return "spell"
    if "战斗" in path:
        return "combat"
    if "怪物" in path or "野兽" in path or "邪神" in path:
        return "monster"
    if "神话典籍" in path or "可怖传说" in path:
        return "tome"
    if "术语表" in path:
        return "glossary"
    return "rule"


def chunk_content_list(blocks: list[Block], type_fn: Optional[TypeFn] = None) -> list[Chunk]:
    """把 MinerU content_list 的 Block 列表切成语义块。

    Args:
        blocks: docparser.Block 列表（MinerU content_list）。
        type_fn: 可选类型判定函数 type_fn(path, name) -> str（默认全 rule）。
                 规则书可注入 `rulebook_type_fn` 按章节关键词定 skill/monster 等。

    规则：
    - 噪声块（header/footnote/page_number）：跳过。
    - 标题块（text+text_level）：截止当前块，开新块，name=标题文本，并更新标题栈（path）。
    - table/image 块：独立成块，截止当前正文块。
    - 正文 text 块：累积进当前块（无当前块则先开无名单块）。
    """
    if type_fn is None:
        type_fn = _default_type_fn
    chunks: list[Chunk] = []
    current: Optional[Chunk] = None
    # 标题栈：维护各级标题文本，重建 path（如 "第三章/3.1 第一步/那些数字意味着什么"）
    stack: list[tuple[int, str]] = []  # (level, title)

    order = 0
    for b in blocks:
        if is_noise(b):
            continue

        if is_title(b):
            if current and current.lines:      # 截止当前累积块
                chunks.append(current); order += 1
                current = None
            lvl = _title_level(b)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, b.text))
            path = "/".join(t for _, t in stack)
            current = Chunk(                    # 新建标题块，正文后续累积进它
                type=type_fn(path, b.text),
                name=b.text, title=b.text, text=b.text,
                page=b.page_idx + 1, start_page=b.page_idx + 1, end_page=b.page_idx + 1,
                path=path, order=order, lines=[b.text],
            )
            continue

        if b.type in _SPECIAL_TYPES:
            if current and current.lines:
                chunks.append(current); order += 1
                current = None
            chunks.append(Chunk(
                type=b.type, name="", title="",
                text=(b.text or ""), page=b.page_idx + 1,
                start_page=b.page_idx + 1, end_page=b.page_idx + 1,
                path="/".join(t for _, t in stack), order=order,
                lines=[b.text] if b.text else [],
            ))
            order += 1
            continue

        # 正文 text 块（lvl 空）
        if not b.text.strip():
            continue
        path = "/".join(t for _, t in stack)
        if current is None:
            current = Chunk(
                type=type_fn(path, ""), name="", title="",
                text=b.text, page=b.page_idx + 1, start_page=b.page_idx + 1,
                end_page=b.page_idx + 1, path=path, order=order, lines=[b.text],
            )
        else:
            current.text += "\n" + b.text
            current.lines.append(b.text)
            current.end_page = b.page_idx + 1

    if current and current.lines:
        chunks.append(current)
    return chunks
