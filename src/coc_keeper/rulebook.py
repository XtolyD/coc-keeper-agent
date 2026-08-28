# -*- coding: utf-8 -*-
"""规则书结构化抽取：把 CoC 7th 规则书 PDF 变成「清洗后、分栏有序、按 TOC 分层」的语料。

用途：M2 RAG 的规则检索。相比 `fulltext.txt`（原始全文），这里：
- 按版面列先左后右重排，保证双栏阅读顺序正确；
- 去掉页眉、页码、译者署名、引用署名、空白块等噪声；
- 用 PDF 内嵌 TOC 建立「章/节/小节」三级结构，每条规则都可回溯到页号。

设计目标：纯函数、可测试；对外只暴露 `extract_pages` / `build_structure` 等，
PDF I/O 与噪声规则集中在这一个模块，方便 RAG 复用与单元测试。

注意：本模块不改变「规则正确性由代码保证」的原则——它只负责把规则原文
变为**可检索**的干净文本，供 `search_rules` 命中段落并引用页号。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ---- 版面阈值（基于 612x792 规则书实测）------------------------------------
TOP_Y_FRACTION = 0.06      # 页眉带：块底 y < 6% 页高
FOOT_Y_FRACTION = 0.93     # 页码带：块顶 y > 93% 页高
COLUMN_MID_FRACTION = 0.5  # 左右栏分界（按块 x 中心）
WIDE_BLOCK_FRACTION = 0.58  # 判定「跨栏宽块」的宽度占比

# ---- 噪声正则 ----------------------------------------------------------------
_TRANSLATOR_RE = re.compile(r"^\s*(译\s*[/／]|译者\s*[:：])")  # 译/xx、译者：xx
# 引文署名：以破折号开头，且含书名号《》或引号“”或句尾译字。
# 注意不能只用「^——」，否则会误删以破折号开头的正文句子
# （如“……更丑陋\n——一团团不定型的黏性黑泥……”）。
_CITATION_RE = re.compile(r"^\s*——.*(?:《[^》]*》|“[^”]*”|译\s*$)")

# ---- 数据模型 ----------------------------------------------------------------
@dataclass
class Section:
    """一个 TOC 节点（章/节/小节）。start_page/end_page 为 1 起的 PDF 页索引。"""
    level: int
    title: str
    start_page: int
    end_page: int = 0
    children: list["Section"] = field(default_factory=list)

    @property
    def page_range(self) -> tuple[int, int]:
        return (self.start_page, self.end_page)


@dataclass
class Block:
    """一页中的一个文本块。坐标为页面坐标（pt）。

    size/font 用于实体分块时的“标题识别”（标题字号更大或字体不同）。
    """
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: Optional[float] = None      # 主字号（整块内最大字号）
    font: Optional[str] = None        # 主字体（按跨度出现次数最多者）

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0


# ---- 块提取与噪声识别 -------------------------------------------------------
def _blocks_from_page(page) -> Iterable[Block]:
    """从 PyMuPDF 页对象取出文本块（丢弃图片块）。"""
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        # 汇总该块的主字号(最大)与主字体(出现跨度最多)
        sizes: list[float] = []
        font_cnt: dict[str, int] = {}
        text_parts = []
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                t = s.get("text", "")
                text_parts.append(t)
                sizes.append(s.get("size", 0.0))
                f = s.get("font", "")
                font_cnt[f] = font_cnt.get(f, 0) + len(t)
        text = "".join(text_parts)
        if not text.strip():
            continue
        x0, y0, x1, y1 = b["bbox"]
        main_font = max(font_cnt, key=font_cnt.get) if font_cnt else None
        yield Block(x0, y0, x1, y1, text, size=max(sizes) if sizes else None, font=main_font)


def _is_noise(block: Block, page_rect) -> bool:
    """判断文本块是否属于噪声（页眉/页码带/译者署名/引用署名）。"""
    W, H = page_rect.width, page_rect.height
    if block.y1 < TOP_Y_FRACTION * H:   # 页眉带
        return True
    if block.y0 > FOOT_Y_FRACTION * H:  # 页码带
        return True
    if _TRANSLATOR_RE.match(block.text):
        return True
    if _CITATION_RE.match(block.text):
        return True
    return False


def classify_columns(
    blocks: list[Block], page_rect, *, col_mid: Optional[float] = None
) -> tuple[list[Block], list[Block], list[Block]]:
    """把文本块分为 (左栏, 右栏, 跨栏宽块)。

    分界默认为页面 x 中心；跨栏宽块（宽度 > 页面 58%）单独返回，
    因为它们既不属于单列，也不适合参与两栏按列排序。
    """
    W = page_rect.width
    mid = col_mid if col_mid is not None else COLUMN_MID_FRACTION * W
    left, right, wide = [], [], []
    for b in blocks:
        if b.width > WIDE_BLOCK_FRACTION * W:
            wide.append(b)
        elif b.cx < mid:
            left.append(b)
        else:
            right.append(b)
    for bucket in (left, right, wide):  # 各栏内部按 y（同行再按 x）排序
        bucket.sort(key=lambda b: (b.y0, b.x0))
    return left, right, wide


def order_lines(blocks: list[Block], page_rect) -> list[str]:
    """返回清洗后、按阅读顺序排列的行文本。

    单栏：整体按 y 排序；双栏：**左列全部读完，再读右列**（column-major），
    跨栏宽块（多为页首标题/页尾表格）按其 y 归入左列流中，避免越位。
    最后对有序块做「残块回合并」（见 merge_fragments）。
    """
    from .merge_fragments import merge_tail_fragments

    left, right, wide = classify_columns(blocks, page_rect)
    two_col = len(left) >= 2 and len(right) >= 2  # 两栏各有内容才算双栏
    if not two_col:
        ordered = sorted(left + right + wide, key=lambda b: (b.y0, b.x0))
    else:
        left_col = sorted(left + wide, key=lambda b: (b.y0, b.x0))
        ordered = left_col + right
    return _flatten(merge_tail_fragments(ordered, page_rect))


def _flatten(ordered: list[Block]) -> list[str]:
    """把块内多行拆开，压成单行列表并去除孤立空白。"""
    lines = []
    for b in ordered:
        for seg in b.text.splitlines():
            seg = seg.strip()
            if seg:
                lines.append(seg)
    return lines


def read_page(page) -> list[str]:
    """单页 → 清洗后的行列表（已按版面顺序）。"""
    page_rect = page.rect
    blocks = [b for b in _blocks_from_page(page) if not _is_noise(b, page_rect)]
    return order_lines(blocks, page_rect)


# ---- TOC → 分级结构 ---------------------------------------------------------
def build_structure(doc) -> list[Section]:
    """把 PDF 内嵌 TOC 转成分级 Section 列表（1 起页码），并补完结束页。"""
    root: list[Section] = []
    stack: list[Section] = []
    for level, title, page in doc.get_toc():
        node = Section(level=level, title=title.strip(), start_page=page)
        while stack and stack[-1].level >= level:
            stack.pop()
        (stack[-1].children if stack else root).append(node)
        stack.append(node)
    _compute_page_ranges(root)
    return root


def _compute_page_ranges(sections: list[Section]) -> None:
    """用「下一个相邻节点起点 - 1」补全每个节点的结束页。"""
    for i, s in enumerate(sections):
        end = sections[i + 1].start_page - 1 if i + 1 < len(sections) else s.start_page
        s.end_page = max(s.start_page, end)
        _compute_page_ranges(s.children)


def extract_pages(doc) -> dict[int, list[str]]:
    """整本规则书 → {pdf页索引(1起): [清洗后行]}。跳过纯图/空页。"""
    pages: dict[int, list[str]] = {}
    for i in range(doc.page_count):
        lines = read_page(doc[i])
        if lines:
            pages[i + 1] = lines
    return pages


def build_page_path_map(sections: list[Section]) -> dict[int, str]:
    """由 TOC 结构生成 {pdf页: 章节路径}。

    每一页归属到「覆盖它的最深 TOC 叶子节点」的路径，形如
    `第十四章/14.1 神话生物`。用于给实体块标注章节归属（path 元数据）。
    """
    pmap: dict[int, str] = {}

    def walk(secs: list[Section], prefix: str) -> None:
        for s in secs:
            cur = f"{prefix}/{s.title}".strip("/") if prefix else s.title
            for p in range(s.start_page, s.end_page + 1):
                pmap[p] = cur
            walk(s.children, cur)

    walk(sections, "")
    return pmap
