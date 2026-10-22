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

from .skill_data import SKILL_BASES, base_skill_values as _catalog_base_skill_values


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

    @classmethod
    def from_dict(cls, data: dict) -> "Attributes":
        values = {name: int(data.get(name, 50)) for name in ("STR", "CON", "DEX", "APP", "POW", "SIZ", "INT", "EDU", "LUCK")}
        return cls(**values)


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


#: 技能基础值由 skills_core.json 派生；None 表示由属性派生。
#: 保留 SKILL_BASES 导出，供职业校验和旧调用方使用。
def base_skill_values(attrs: Attributes) -> dict[str, int]:
    """计算各技能基础值（闪避 = DEX/2，母语 = EDU）。"""
    return _catalog_base_skill_values(attrs)


@dataclass
class CharacterSheet:
    """调查员角色卡。当前值（hp/mp/san/luck）为 None 时默认取上限。"""
    name: str = "调查员"
    age: int = 30
    attributes: Attributes = field(default_factory=Attributes)
    skills: dict[str, int] = field(default_factory=dict)
    occupation_id: Optional[int] = None
    occupation_name: str = ""
    occupation_skills: list[str] = field(default_factory=list)
    occupation_points: dict[str, int] = field(default_factory=dict)
    interest_points: dict[str, int] = field(default_factory=dict)
    occupation_skill_cap: int = 70
    non_occupation_skill_cap: int = 60
    credit_rating_min: int = 0
    credit_rating_max: int = 99
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
            "current": {
                "hp": self.hp, "mp": self.mp, "san": self.san, "luck": self.luck,
            },
            "occupation": {
                "id": self.occupation_id,
                "name": self.occupation_name,
                "skills": list(self.occupation_skills),
                "skill_cap": self.occupation_skill_cap,
                "other_skill_cap": self.non_occupation_skill_cap,
                "credit_rating": [self.credit_rating_min, self.credit_rating_max],
            },
            "allocation": {
                "occupation_points": dict(self.occupation_points),
                "interest_points": dict(self.interest_points),
            },
            "skills": dict(self.skills),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterSheet":
        """从 ``to_dict`` 输出恢复角色卡，忽略派生字段以避免重复来源。"""
        attrs = Attributes.from_dict(data.get("attributes", {}))
        current = data.get("current", {})
        derived = data.get("derived", {})
        occupation = data.get("occupation", {})
        allocation = data.get("allocation", {})
        credit_range = occupation.get("credit_rating", [0, 99]) if isinstance(occupation, dict) else [0, 99]

        def current_value(name: str, fallback: int | None = None) -> int | None:
            value = current.get(name.lower())
            if value is not None:
                return int(value)
            raw = derived.get(name)
            if isinstance(raw, str) and "/" in raw:
                return int(raw.split("/", 1)[0])
            return fallback

        return cls(
            name=str(data.get("name", "调查员")), age=int(data.get("age", 30)),
            attributes=attrs, skills={k: int(v) for k, v in data.get("skills", {}).items()},
            occupation_id=int(occupation["id"]) if isinstance(occupation, dict) and occupation.get("id") is not None else None,
            occupation_name=str(occupation.get("name", "")) if isinstance(occupation, dict) else str(occupation or ""),
            occupation_skills=list(occupation.get("skills", [])) if isinstance(occupation, dict) else [],
            occupation_points={k: int(v) for k, v in allocation.get("occupation_points", {}).items()},
            interest_points={k: int(v) for k, v in allocation.get("interest_points", {}).items()},
            occupation_skill_cap=int(occupation.get("skill_cap", 70)) if isinstance(occupation, dict) else 70,
            non_occupation_skill_cap=int(occupation.get("other_skill_cap", 60)) if isinstance(occupation, dict) else 60,
            credit_rating_min=int(credit_range[0]) if credit_range else 0,
            credit_rating_max=int(credit_range[1]) if len(credit_range) > 1 else 99,
            hp=current_value("HP"), mp=current_value("MP"), san=current_value("SAN"),
            luck=int(current.get("luck", data.get("luck", data.get("attributes", {}).get("LUCK", attrs.LUCK)))),
        )


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


def generate_character_candidates(
    name: str = "调查员",
    age: int = 30,
    *,
    count: int = 5,
    rng: Optional[random.Random] = None,
) -> list[CharacterSheet]:
    """生成多套完整属性候选，供玩家选择后再分配技能点。"""
    if not 1 <= int(count) <= 20:
        raise ValueError("候选数量必须为 1..20")
    rng = rng or random
    return [create_character(name=name, age=age, rng=rng) for _ in range(int(count))]


def skill_point_budget(attrs: Attributes) -> int:
    """旧版兼容总池：职业点 EDU×4，加兴趣点 INT×2。"""
    return attrs.EDU * 4 + attrs.INT * 2


def allocate_occupation_points(
    sheet: CharacterSheet,
    occupation_id: int,
    occupation_skills: list[str],
    occupation_points: dict[str, int],
    interest_points: dict[str, int],
    *,
    occupation_skill_cap: int = 70,
    non_occupation_skill_cap: int = 60,
) -> CharacterSheet:
    """按职业模板分别分配职业点与兴趣点。"""
    from .occupations import (
        get_occupation, interest_point_budget, occupation_point_budget,
        validate_occupation_skills,
    )

    if not 1 <= int(non_occupation_skill_cap) <= int(occupation_skill_cap) <= 100:
        raise ValueError("技能上限必须满足 1 <= 非本职上限 <= 本职上限 <= 100")
    occupation = get_occupation(occupation_id)
    selected = validate_occupation_skills(occupation, occupation_skills)
    main_skills = set(selected)
    bases = base_skill_values(sheet.attributes)

    def normalize(points: dict[str, int], label: str) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for raw_name, raw_value in points.items():
            name = str(raw_name).strip()
            if name not in bases:
                raise ValueError(f"{label}包含未知技能: {name}")
            value = int(raw_value)
            if value < 0:
                raise ValueError(f"技能「{name}」的{label}不能为负数")
            if value:
                normalized[name] = value
        return normalized

    occupational = normalize(occupation_points, "职业点")
    interests = normalize(interest_points, "兴趣点")
    invalid_occupational = set(occupational).difference(main_skills)
    if invalid_occupational:
        raise ValueError(f"职业点只能分配给本职技能: {', '.join(sorted(invalid_occupational))}")
    if occupational.get("克苏鲁神话", 0) or interests.get("克苏鲁神话", 0):
        raise ValueError("创建调查员时不能给克苏鲁神话分配技能点")

    occupation_budget = occupation_point_budget(sheet.attributes, occupation)
    interest_budget = interest_point_budget(sheet.attributes)
    if sum(occupational.values()) > occupation_budget:
        raise ValueError(f"职业点超出预算: 已用 {sum(occupational.values())}，可用 {occupation_budget}")
    if sum(interests.values()) > interest_budget:
        raise ValueError(f"兴趣点超出预算: 已用 {sum(interests.values())}，可用 {interest_budget}")
    if occupational.get("信用评级", 0) < occupation.credit_min:
        raise ValueError(f"信用评级必须先使用职业点达到 {occupation.credit_min}")

    skills: dict[str, int] = {}
    for name, base in bases.items():
        value = base + occupational.get(name, 0) + interests.get(name, 0)
        configured_cap = occupation_skill_cap if name in main_skills else non_occupation_skill_cap
        cap = max(base, configured_cap)
        if value > cap:
            kind = "本职" if name in main_skills else "非本职"
            raise ValueError(f"技能「{name}」超过{kind}技能上限 {cap}")
        skills[name] = value
    if not occupation.credit_min <= skills["信用评级"] <= occupation.credit_max:
        raise ValueError(f"信用评级必须在职业范围 {occupation.credit_min}-{occupation.credit_max} 内")

    sheet.occupation_id = occupation.id
    sheet.occupation_name = occupation.name
    sheet.occupation_skills = list(selected)
    sheet.occupation_points = occupational
    sheet.interest_points = interests
    sheet.occupation_skill_cap = int(occupation_skill_cap)
    sheet.non_occupation_skill_cap = int(non_occupation_skill_cap)
    sheet.credit_rating_min = occupation.credit_min
    sheet.credit_rating_max = occupation.credit_max
    sheet.skills = skills
    return sheet


def allocate_skill_points(sheet: CharacterSheet, targets: dict[str, int]) -> CharacterSheet:
    """把目标技能值应用到角色卡，并校验基础值、单项上限和总点数。"""
    bases = base_skill_values(sheet.attributes)
    normalized = dict(bases)
    spent = 0
    for skill, raw_value in targets.items():
        name = str(skill).strip()
        if name not in bases:
            raise ValueError(f"未知技能: {name}")
        value = int(raw_value)
        if not bases[name] <= value <= 100:
            raise ValueError(f"技能「{name}」必须在基础值 {bases[name]} 与 100 之间")
        normalized[name] = value
        spent += value - bases[name]
    budget = skill_point_budget(sheet.attributes)
    if spent > budget:
        raise ValueError(f"技能点超出预算: 已用 {spent}，可用 {budget}")
    sheet.skills = normalized
    return sheet


def skill_points_spent(sheet: CharacterSheet) -> int:
    if sheet.occupation_points or sheet.interest_points:
        return occupation_points_spent(sheet) + interest_points_spent(sheet)
    bases = base_skill_values(sheet.attributes)
    return sum(max(0, int(sheet.skills.get(name, base)) - base) for name, base in bases.items())


def occupation_points_spent(sheet: CharacterSheet) -> int:
    return sum(max(0, int(value)) for value in sheet.occupation_points.values())


def interest_points_spent(sheet: CharacterSheet) -> int:
    return sum(max(0, int(value)) for value in sheet.interest_points.values())
