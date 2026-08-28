# -*- coding: utf-8 -*-
"""规则书「内容实体」分块器（方案 B：实体识别）。

把清洗后、按页组织的内容，按「内容实体」（怪物/技能/法术/小节/表格/词条）切分。

判界信号（实测校准，见 docs/retrieval-spec.md）：
- 页级版式：短块占比高 → 列表/表格页，整页保留（如技能列表）；否则按实体切。
- 节/章标题：字号明显大于正文（size≥12）。
- 实体名（怪物/邪神/妖魔/野兽）：窄块 + 短 + 无句读，且**不在**排除清单、不命中属性数据特征。
- 排除清单：怪物块内小标题（攻击/特殊能力/教团/其他特性…）、属性数据行（STR/CON/躲避…）、
  引文尾（《…》/括号残留）。

纯函数、可测试。对外提供：
  from coc_keeper.chunker import split_blocks_from_lines  # 行层（无排版）
  from coc_keeper.chunker import classify_name, is_monster_name
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---- 基准（来自规则书实测）--------------------------------------------------
TITLE_SIZE_MIN = 12.0           # 节/章标题字号阈值
ENTITY_NAME_WIDTH = 0.20        # 窄块宽度占比阈值（<20% 页宽 = 可能实体名）
LIST_PAGE_SHORT_RATIO = 0.50    # 页级：短块占比高于此 → 列表/表格页
SHORT_BLOCK_LEN = 12            # 短块：去空白字符数上限
COMPACT_MAX_FOR_NAME = 14       # 实体名：去空白字符数上限

# ---- 正则 --------------------------------------------------------------------
_SKILL_ITEM_RE = re.compile(r"^[^（()]{1,20}[（(][^（()]{1,20}[）)]$")
_ATTR_RE = re.compile(r"^(STR|CON|DEX|INT|POW|SIZ|EDU|APP|LUCK|HP)\b")
_ATTR_DICE_RE = re.compile(r"^(STR|CON|DEX|INT|POW|SIZ|EDU|APP|LUCK)\s*(N/A|[\d]|\d+\s*[（(])")
_STAT_LINE_RE = re.compile(r"(STR|CON|DEX|INT|POW|SIZ|HP|躲避|闪避|护甲|伤害加[成值]|魔法值|每回合|[0-9]+[（(][0-9]|\([0-9]+/[0-9]+\)|N/A)")
# 引文尾残段：《…》 或 只有 "）" 结尾的碎片
_CITATION_FRAG_RE = re.compile(r"^[《「].{0,10}[》」]$|^[（(]?[^（()]{0,8}[）)]$|^[的啦着子里]？?$")

# ---- 排除清单（怪物块内小标题 / 章节分隔 / 固定词）--------------------------
_KNOWN_SUBHEAD = {
    "攻击", "特殊能力", "教团", "其他特性", "人类形态", "怪物形态", "战斗",
    "法术", "魔法值", "属性平均值掷骰", "平均掷骰", "伤害", "移动",
    "战斗方式", "怪物和反击", "杀死怪物", "怪物法术", "属性",
}
# 章节分隔标题（结构边界，作为小节而非怪物实体）
_SECTION_MARKER_RE = re.compile(r"^1[45]\.\d+")

# 引文作品尾（作者名/书名残段，排除）
_CITATION_SURNAME = {"洛夫克拉夫特", "德雷斯", "坎贝尔", "史密斯", "马钦",
                     "拉姆利", "布赖恩", "穆雷", "朗", "贝绍普", "扎利亚"}

# 描述/数值类子串：出现在窄块里 → 该块不是实体名（是战斗描述、属性、段标题）
_DESCRIPTIVE_TOKENS = (
    "平均", "加值", "加成", "掷骰", "伤害", "造成", "目标", "战技",
    "每回合", "攻击", "魔法", "移动", "吞噬", "吸附", "腐蚀", "扑咬",
    "（目标", "（单一", "（见上文", "点伤害", "值）", "为合适", "或者其他",
    "对魔力", "修正", "次）", "点）", "物馆里", "的诅咒", "穿越银匙",
    "效果", "架构", "可选规则",
)


def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _is_short_block(c: str) -> bool:
    """短块：去空白 ≤12 字且无句读（用于页级版式统计）。"""
    return 0 < len(c) <= SHORT_BLOCK_LEN and not any(p in c for p in "。，；：！？")


def is_stat_line(text: str) -> bool:
    """是否为属性/战斗数据行。"""
    c = _compact(text)
    if not c:
        return False
    if _ATTR_DICE_RE.match(c):
        return True
    if _STAT_LINE_RE.search(c):
        return True
    return False


def is_monster_name(text: str, width: float = 0.0, page_width: float = 612.0) -> bool:
    """判断窄短块是否为「实体名」（怪物/邪神/妖魔/野兽）。"""
    c = _compact(text)
    if not c:
        return False
    # 长度 / 标点 / 小标题 / 属性数据行 / 引文残段 一律排除
    if len(c) > COMPACT_MAX_FOR_NAME:
        return False
    if any(p in c for p in "。，；：！？《》"):
        return False
    if c in _KNOWN_SUBHEAD:
        return False
    if is_stat_line(text):
        return False
    if _CITATION_FRAG_RE.match(c):
        return False
    # 描述/数值/动作类子串 → 非实体名（战斗描述、属性、段标题）
    if any(t in c for t in _DESCRIPTIVE_TOKENS):
        return False
    # 含全角括号 → 属性/注释/引文残段（如 `*（是爬行动物形态下的属性）`）
    if "（" in c or "）" in c:
        return False
    # 含「怪物」等描述性词 → 非实体名（真名不含「怪物」）
    if "怪物" in c or "超越" in c:
        return False
    # 数字/符号开头 → 属性/破碎片段
    if c[:1].isdigit() or c[:1] in "（（\"'*":
        return False
    # 含数字的短块 → 属性/数值碎片
    if any(ch.isdigit() for ch in c):
        return False
    # 单字停用（值/击/看/敌/神/类 等）→ 非实体名
    if len(c) == 1 and c in "值击看敌神类长大大个被把为":
        return False
    return True


def classify_name(text: str) -> str:
    """给候选名字定一块雏形类型（精细分类在并入 path 后由章节上下文决定）。"""
    return "monster"


@dataclass
class Chunk:
    """一个可检索的规则实体块。"""
    type: str                # monster/skill/spell/combat/rule/table/glossary
    name: str                # 实体名（怪物名/技能名/小节标题）
    title: str               # 原始标题行
    text: str                # 实体正文（含标题行）
    page: int                # 所在 PDF 页（1 起）
    path: str = ""           # 章节路径
    order: int = 0
    lines: list[str] = field(default_factory=list)


@dataclass
class PBlock:
    """一页中一个版块及其排版信号。"""
    text: str
    size: Optional[float] = None
    font: Optional[str] = None
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    width: float = 0.0
    page_width: float = 612.0

    @property
    def compact(self) -> str:
        return _compact(self.text)

    def is_title_size(self) -> bool:
        return self.size is not None and self.size >= TITLE_SIZE_MIN

    def is_monster_name(self) -> bool:
        return is_monster_name(self.text, self.width, self.page_width)
