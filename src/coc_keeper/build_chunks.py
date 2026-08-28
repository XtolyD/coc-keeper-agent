# -*- coding: utf-8 -*-
"""规则书「内容实体」块的编排器：页内切分 + 跨页合并。

吃 `read_page()` 产出的清洗行 + TOC 路径，产出可检索的实体 Chunk：
- 列表/表格页 → 整页一个 `table` 块。
- 正文页 → 识别实体名（monster）或按小节标题切块；其余归为 `rule`。
- 跨页：同一实体名跨页延续时，合并为一块（拜亚基跨 p252-253）。

离线一次性运行，产出 `rules_chunks.json` + 序列化 BM25 索引。
"""
from __future__ import annotations

import re
from pathlib import Path

from .chunker import is_monster_name, _is_short_block

# 技能条目：`名称（基础值）`（含 括号内 %/一半DEX/专业化/EDU/各种各样 等）
_SKILL_ITEM_RE = re.compile(r"^[^（()]{1,20}[（(][^（()]{0,20}[）)]$")


def _is_skill_item(line: str) -> bool:
    c = "".join(line.split())
    if not _SKILL_ITEM_RE.match(c):
        return False
    if len(c) > 20:
        return False
    return True


def _boundary_fn(path: str):
    """根据章节路径选择「边界行」检测函数（实体名 or 技能条目）。"""
    if "技能" in path:
        return _is_skill_item
    return _looks_like_entity_name

# 排除不参与规则检索的前置/后置章节（目录/版权/使用说明/译者署名等）
EXCLUDED_PATHS = (
    "克苏鲁的呼唤 第七版", "使用说明", "前言", "目录",
    "译名表", "汉化进度表",
)


def _is_excluded_path(path: str) -> bool:
    return any(x in path for x in EXCLUDED_PATHS)


def _section_type(path: str, name: str) -> str:
    """按章节路径给块定类型（决定实体语义，而非仅靠名字）。"""
    if "技能" in path:
        return "skill"
    if "追逐" in path:
        return "rule"
    if "战斗" in path:
        return "combat"
    if "法术" in path:
        return "spell"
    if "神话典籍" in path or "可怖传说" in path:
        return "tome"
    if "术语表" in path:
        return "glossary"
    if "怪物" in path or "野兽" in path or "邪神" in path or "经典妖魔" in path:
        return "monster"
    return "rule"


def _looks_like_entity_name(line: str) -> bool:
    """单行是否为实体名（怪物名/邪神名/小节标题）。"""
    return is_monster_name(line, width=0, page_width=1)


def _is_list_page(lines: list[str]) -> bool:
    total = len(lines)
    if total == 0:
        return False
    short = sum(1 for l in lines if _is_short_block("".join(l.split())))
    return (short / total) >= 0.50


# 表格/词表行判定
# 强表头：`表XV：…`、`实体 发音`、`体格 真实世界` 等 —— 一旦命中，会“吞并”后续表格区。
_TABLE_HEADER_RE = re.compile(r"(^表[XVXIV]+[：:]|实体\s+发音|体格\s+真实世界)")


def _is_body_paragraph(line: str) -> bool:
    """正文长句：字数较多、含多个中文块、且不含英文（英文词多为表格单元格）。"""
    c = "".join(line.split())
    cn = len(re.findall(r"[\u4e00-\u9fff]+", line))
    en = len(re.findall(r"[A-Za-z][A-Za-z-]+", line))
    return len(c) > 18 and cn >= 2 and en < 1


def _split_table_region(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """把一页切成 (前置正文, 表格/词表区, 后置正文)。

    命中强表头后，吞并后续行直到“正文长句”回归（视为表格结束）。
    """
    # 只靠强表头触发（表X/实体 发音/体格 真实世界）。
    # 不再用“双语多列”作为 fallback，因为正文里的 `STR/HP/ID` 等缩写
    # 会被误判成表格单元格（如拜亚基的紧咬技能描述）。
    start = next((i for i, l in enumerate(lines) if _TABLE_HEADER_RE.search(l)), None)
    if start is None:
        return lines, [], []
    # 表格区结束：遇到正文长句（1 行即视为回归）
    end = start
    for j in range(start, len(lines)):
        if _is_body_paragraph(lines[j]):
            break
        end = j
    return lines[:start], lines[start:end + 1], lines[end + 1:]


def _chunk_body(lines: list[str], page_no: int, path: str, order: int) -> tuple[list[dict], int]:
    """把一段正文行切分成实体块（边界行换块），返回 (块列表, 新 order)。"""
    out: list[dict] = []
    current: dict | None = None
    boundary = _boundary_fn(path)
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        is_entity = boundary(ln)
        if is_entity:
            if current and current["lines"]:
                out.append(current); order += 1
            typ = _section_type(path, ln)
            current = {
                "type": typ, "name": ln, "title": ln,
                "text": ln, "page": page_no, "start_page": page_no, "end_page": page_no,
                "path": path, "order": order, "lines": [ln],
            }
        else:
            if current is None:
                current = {
                    "type": _section_type(path, ""), "name": "", "title": "",
                    "text": ln, "page": page_no, "start_page": page_no, "end_page": page_no,
                    "path": path, "order": order, "lines": [ln],
                }
            else:
                current["text"] += "\n" + ln
                current["lines"].append(ln)
                current["end_page"] = page_no
    if current and current["lines"]:
        out.append(current); order += 1
    return out, order


def chunk_pages(pages: dict[int, list[str]], page_paths: dict[int, str]) -> list[dict]:
    """把 {页: 行} 切成实体块列表（跨页合并）。"""
    chunks: list[dict] = []
    order = 0

    for page_no in sorted(pages):
        lines = pages[page_no]
        path = page_paths.get(page_no, "")
        if _is_excluded_path(path):
            continue

        page_type = "list" if _is_list_page(lines) else "body"
        if page_type == "list":
            chunks.append({
                "type": "table", "name": lines[0][:20], "title": lines[0][:20],
                "text": "\n".join(lines), "page": page_no, "start_page": page_no, "end_page": page_no,
                "path": path, "order": order, "lines": list(lines),
            })
            order += 1
            continue

        # 正文页：若检测到表格/词表区，先切出 table 块，前后正文单独处理。
        pre, table_region, post = _split_table_region(lines)
        for seg_lines in (pre, post):
            if seg_lines:
                seg_chunks, order = _chunk_body(seg_lines, page_no, path, order)
                chunks.extend(seg_chunks)
        if table_region:
            chunks.append({
                "type": "table", "name": table_region[0][:20], "title": table_region[0][:20],
                "text": "\n".join(l.strip() for l in table_region),
                "page": page_no, "start_page": page_no, "end_page": page_no,
                "path": path, "order": order, "lines": list(table_region),
            })
            order += 1

    # 跨页合并：页首无名单块（上一实体跨页延续）并入上一实体。
    return _merge_cross_page(chunks)


def _merge_cross_page(chunks: list[dict]) -> list[dict]:
    """跨页合并：若某块 name 为空（页首无名字的延续块），并入前一块已命名实体。"""
    merged: list[dict] = []
    for c in chunks:
        if merged and c.get("name") == "" and merged[-1].get("name"):
            # 并入上一实体
            prev = merged[-1]
            prev["text"] = (prev["text"] + "\n" + c["text"]).strip()
            prev["lines"].extend(c["lines"])
            prev["end_page"] = max(prev.get("end_page", prev["page"]), c.get("end_page", c["page"]))
            continue
        merged.append(c)
    return merged
