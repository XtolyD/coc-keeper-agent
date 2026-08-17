# -*- coding: utf-8 -*-
"""调查员角色卡：属性、衍生属性、技能、建卡。

规则出处：《COC7th 核心规则书 v1.2.1》
- 第三章 创建调查员（p23-41）
- 附录「速查：半值和五分之一值」（p370）

1920s 标准建卡（已对照规则书核实）：
- STR/CON/DEX/APP/POW：3d6 × 5（范围 15-90）
- SIZ/INT/EDU：(2d6+6) × 5（范围 40-90）
- LUCK：3d6 × 5
- HP = (CON + SIZ) // 10；MP = POW // 5；初始 SAN = POW
- 伤害加值/体格：由 STR + SIZ 查表Ⅰ
- 移动 MOV：由 STR/DEX 与 SIZ 关系决定，年龄 40 岁起递减
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .dice import half


@dataclass
class Attributes:
    """八大属性 + 幸运（均为百分比值；怪物可超过 100）。"""
    STR: int = 50
    CON: int = 50
    DEX: int = 50
    APP: int = 50
    POW: int = 50
    SIZ: int = 50
    INT: int = 50
    EDU: int = 50
    LUCK: int = 50


def damage_bonus_and_build(str_plus_siz: int) -> tuple[str, int]:
    """表Ⅰ：伤害加值和体格表。返回 (伤害加值表达式, 体格)。"""
    if str_plus_siz <= 64:
        return "-2", -2
    if str_plus_siz <= 84:
        return "-1", -1
    if str_plus_siz <= 124:
        return "0", 0
    if str_plus_siz <= 164:
        return "+1d4", 1
    if str_plus_siz <= 204:
        return "+1d6", 2
    if str_plus_siz <= 284:
        return "+2d6", 3
    if str_plus_siz <= 364:
        return "+3d6", 4
    if str_plus_siz <= 444:
        return "+4d6", 5
    if str_plus_siz <= 524:
        return "+5d6", 6
    # 超过 524：合计值每超 80（不足 80 按 80 算）额外 +1d6 与 +1 体格
    extra = (str_plus_siz - 524 + 79) // 80
    return f"+{5 + extra}d6", 6 + extra


def movement(STR: int, DEX: int, SIZ: int, age: int = 30) -> int:
    """移动速度 MOV。年龄 40 岁起每 10 年减 1，最多减 5。"""
    if STR > SIZ and DEX > SIZ:
        m = 9
    elif STR < SIZ and DEX < SIZ:
        m = 7
    else:
        m = 8
    if age >= 40:
        m -= min((age - 30) // 10, 5)
    return m


#: 1920s 标准技能列表及其基础值（%）；None 表示由属性派生。
SKILL_BASES: dict[str, Optional[int]] = {
    "会计": 5, "人类学": 1, "估价": 5, "考古学": 1,
    "艺术/手艺": 5, "魅惑": 15, "攀爬": 20, "信用评级": 0,
    "克苏鲁神话": 0, "乔装": 5, "闪避": None, "汽车驾驶": 20,
    "电气维修": 10, "话术": 5, "格斗（斗殴）": 25,
    "射击（手枪）": 20, "射击（步枪/霰弹枪）": 25, "急救": 30,
    "历史": 5, "恐吓": 15, "跳跃": 20, "母语": None, "外语": 1,
    "法律": 5, "图书馆使用": 20, "聆听": 20, "锁匠": 1,
    "机械维修": 10, "医学": 1, "博物学": 10, "导航": 10,
    "神秘学": 5, "操作重型机械": 1, "说服": 10,
    "驾驶（飞行/航海）": 1, "精神分析": 1, "心理学": 10,
    "读唇": 1, "骑术": 5, "科学": 1, "妙手": 10, "侦查": 25,
    "潜行": 20, "生存": 10, "游泳": 20, "投掷": 20, "追踪": 10,
}


def base_skill_values(attrs: Attributes) -> dict[str, int]:
    """计算各技能基础值（闪避 = DEX/2，母语 = EDU）。"""
    out: dict[str, int] = {}
    for name, base in SKILL_BASES.items():
        if base is None:
            if name == "闪避":
                out[name] = half(attrs.DEX)
            elif name == "母语":
                out[name] = attrs.EDU
            else:
                out[name] = 0
        else:
            out[name] = base
    return out


@dataclass
class CharacterSheet:
    """调查员角色卡。当前值（hp/mp/san/luck）为 None 时默认取上限。"""
    name: str = "调查员"
    age: int = 30
    attributes: Attributes = field(default_factory=Attributes)
    skills: dict[str, int] = field(default_factory=dict)
    hp: Optional[int] = None
    mp: Optional[int] = None
    san: Optional[int] = None
    luck: Optional[int] = None

    def __post_init__(self):
        if not self.skills:
            self.skills = base_skill_values(self.attributes)
        if self.hp is None:
            self.hp = self.hp_max
        if self.mp is None:
            self.mp = self.mp_max
        if self.san is None:
            self.san = self.san_max
        if self.luck is None:
            self.luck = self.attributes.LUCK

    # ---- 衍生上限 ----
    @property
    def hp_max(self) -> int:
        return (self.attributes.CON + self.attributes.SIZ) // 10

    @property
    def mp_max(self) -> int:
        return self.attributes.POW // 5

    @property
    def san_max(self) -> int:
        return self.attributes.POW  # 初始理智 = POW

    @property
    def db(self) -> str:
        return damage_bonus_and_build(self.attributes.STR + self.attributes.SIZ)[0]

    @property
    def build(self) -> int:
        return damage_bonus_and_build(self.attributes.STR + self.attributes.SIZ)[1]

    @property
    def mov(self) -> int:
        return movement(self.attributes.STR, self.attributes.DEX, self.attributes.SIZ, self.age)

    def to_dict(self) -> dict:
        """摘要（供展示或作为工具返回值交给 LLM）。"""
        a = self.attributes
        return {
            "name": self.name,
            "age": self.age,
            "attributes": {
                "STR": a.STR, "CON": a.CON, "DEX": a.DEX, "APP": a.APP,
                "POW": a.POW, "SIZ": a.SIZ, "INT": a.INT, "EDU": a.EDU,
                "LUCK": self.luck,
            },
            "derived": {
                "HP": f"{self.hp}/{self.hp_max}",
                "MP": f"{self.mp}/{self.mp_max}",
                "SAN": f"{self.san}/{self.san_max}",
                "DB": self.db,
                "Build": self.build,
                "MOV": self.mov,
            },
            "skills": dict(self.skills),
        }


def roll_attributes(rng: Optional[random.Random] = None) -> Attributes:
    """1920s 标准属性投骰。"""
    rng = rng or random

    def pct_3d6() -> int:
        return sum(rng.randint(1, 6) for _ in range(3)) * 5

    def pct_2d6p6() -> int:
        return (sum(rng.randint(1, 6) for _ in range(2)) + 6) * 5

    return Attributes(
        STR=pct_3d6(), CON=pct_3d6(), DEX=pct_3d6(), APP=pct_3d6(), POW=pct_3d6(),
        SIZ=pct_2d6p6(), INT=pct_2d6p6(), EDU=pct_2d6p6(), LUCK=pct_3d6(),
    )


def create_character(name: str = "调查员", age: int = 30, rng: Optional[random.Random] = None) -> CharacterSheet:
    """随机生成一名调查员（属性随机，技能为基础值）。"""
    return CharacterSheet(name=name, age=age, attributes=roll_attributes(rng))
