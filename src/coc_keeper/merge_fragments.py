# -*- coding: utf-8 -*-
"""残块回合并：把「紧贴上一块尾部的孤立碎片」拼回上一块。

成因：双栏/跨栏排版会把一行的末尾文字裁成独立短块（如 `理智丧失：…点理智` 的
`值`），重排后成为孤立行。合并规则（实测 gap 判别性强）：

- **残块**：去空白 ≤3 字，且 `gap_y ≤ 5`（紧贴上一块底部，间距 4 为同行换行）。
- 判据 `gap_y`：实测 `4`（143 次）= 同行尾部截断该合并；`21`（140 次）= 正常段落
  **不**合并；负值 = 分栏拼接点，跳过。
- 要求上一块是「正常宽度行」（宽度 > 页面 20%），避免把实体标签（马/狗/蛇）
  误并进属性行。
"""
from __future__ import annotations

from typing import Optional

from .rulebook import Block  # 复用块定义

MAX_FRAG_LEN = 3          # 残块去空白后字符上限
Y_GAP_MAX = 6.0           # 允许的纵向间隙（pt）：≤6 视为同行尾部截断
MIN_PREV_WIDTH = 0.10     # 上一块宽度需超过页宽比例，才视为正常正文行


def _is_fragment(block: Block, page_rect) -> bool:
    c = "".join(block.text.split())
    if not c:
        return False
    if len(c) > MAX_FRAG_LEN:
        return False
    # 残块通常无句读或只是句末标点；若是纯标点/数字碎片也归为残块
    # （实体名单字 马/狗/蛇/狼/鸟 不算残块，因为它们是独立实体标签，
    #   且其 gap 通常是 21 而非 4——靠 gap 判据区分。）
    return True


def merge_tail_fragments(ordered: list[Block], page_rect) -> list[Block]:
    """在已按阅读顺序排好的块序列上，把孤立残块拼回上一块。"""
    if not ordered:
        return ordered
    W = page_rect.width
    result: list[Block] = []
    for b in ordered:
        if result and _is_fragment(b, page_rect):
            prev = result[-1]
            # 上一块需是正常宽度正文行（非碎片/属性短行）
            if (prev.x1 - prev.x0) > MIN_PREV_WIDTH * W:
                gap = b.y0 - prev.y1
                if 0 <= gap <= Y_GAP_MAX:
                    # 拼回上一块末尾
                    merged_text = prev.text.rstrip() + b.text.strip()
                    result[-1] = Block(
                        prev.x0, prev.y0, max(prev.x1, b.x1), prev.y1,
                        merged_text, size=prev.size, font=prev.font,
                    )
                    continue
        result.append(b)
    return result
