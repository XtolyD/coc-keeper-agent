# -*- coding: utf-8 -*-
"""CoC 7th 职业模板、职业点公式和本职技能选择约束。"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

from .character import Attributes, SKILL_BASES


OCCUPATION_SKILL_CAP = 70
NON_OCCUPATION_SKILL_CAP = 60


@dataclass(frozen=True)
class SkillChoiceGroup:
    count: int
    skills: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"count": self.count, "skills": list(self.skills)}


@dataclass(frozen=True)
class Occupation:
    id: int
    name: str
    credit_min: int
    credit_max: int
    point_formula: str
    point_formula_label: str
    skill_template: str
    fixed_skills: tuple[str, ...]
    choice_groups: tuple[SkillChoiceGroup, ...]
    free_choice_count: int

    @classmethod
    def from_dict(cls, data: dict) -> "Occupation":
        return cls(
            id=int(data["id"]), name=str(data["name"]),
            credit_min=int(data["credit_min"]), credit_max=int(data["credit_max"]),
            point_formula=str(data["point_formula"]),
            point_formula_label=str(data["point_formula_label"]),
            skill_template=str(data["skill_template"]),
            fixed_skills=tuple(str(item) for item in data["fixed_skills"]),
            choice_groups=tuple(SkillChoiceGroup(int(item["count"]), tuple(item["skills"])) for item in data["choice_groups"]),
            free_choice_count=int(data["free_choice_count"]),
        )

    def to_dict(self, attrs: Attributes | None = None) -> dict:
        payload = {
            "id": self.id, "name": self.name,
            "credit_min": self.credit_min, "credit_max": self.credit_max,
            "point_formula": self.point_formula,
            "point_formula_label": self.point_formula_label,
            "skill_template": self.skill_template,
            "fixed_skills": list(self.fixed_skills),
            "choice_groups": [group.to_dict() for group in self.choice_groups],
            "free_choice_count": self.free_choice_count,
        }
        if attrs is not None:
            payload["occupation_point_budget"] = occupation_point_budget(attrs, self)
        return payload


def _load() -> tuple[Occupation, ...]:
    path = Path(__file__).resolve().parent / "data" / "occupations.json"
    return tuple(Occupation.from_dict(item) for item in json.loads(path.read_text(encoding="utf-8")))


OCCUPATIONS = _load()
_BY_ID = {occupation.id: occupation for occupation in OCCUPATIONS}


def list_occupations() -> tuple[Occupation, ...]:
    return OCCUPATIONS


def get_occupation(occupation_id: int) -> Occupation:
    try:
        return _BY_ID[int(occupation_id)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"未知职业 ID: {occupation_id}") from exc


def _eval_formula(node: ast.AST, values: dict[str, int]) -> int:
    if isinstance(node, ast.Expression):
        return _eval_formula(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return int(node.value)
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        left, right = _eval_formula(node.left, values), _eval_formula(node.right, values)
        return left + right if isinstance(node.op, ast.Add) else left * right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "MAX":
        return max(_eval_formula(argument, values) for argument in node.args)
    raise ValueError("职业点公式包含不支持的表达式")


def occupation_point_budget(attrs: Attributes, occupation: Occupation) -> int:
    values = {name: int(getattr(attrs, name)) for name in ("STR", "CON", "DEX", "APP", "POW", "SIZ", "INT", "EDU")}
    return _eval_formula(ast.parse(occupation.point_formula, mode="eval"), values)


def interest_point_budget(attrs: Attributes) -> int:
    return attrs.INT * 2


def _groups_can_consume(groups: tuple[SkillChoiceGroup, ...], remaining: set[str], index: int = 0) -> bool:
    if index >= len(groups):
        return True
    group = groups[index]
    choices = sorted(remaining.intersection(group.skills))
    for selected in combinations(choices, group.count):
        if _groups_can_consume(groups, remaining.difference(selected), index + 1):
            return True
    return False


def validate_occupation_skills(occupation: Occupation, selected: Iterable[str]) -> tuple[str, ...]:
    selected_set = {str(skill).strip() for skill in selected if str(skill).strip()}
    unknown = selected_set.difference(SKILL_BASES)
    if unknown:
        raise ValueError(f"本职技能包含未知技能: {', '.join(sorted(unknown))}")
    fixed = set(occupation.fixed_skills)
    missing = fixed.difference(selected_set)
    if missing:
        raise ValueError(f"缺少职业必选技能: {', '.join(sorted(missing))}")
    group_slots = sum(group.count for group in occupation.choice_groups)
    expected = len(fixed) + group_slots + occupation.free_choice_count
    if len(selected_set) != expected:
        raise ValueError(f"本职技能数量应为 {expected}，当前为 {len(selected_set)}")
    remaining = selected_set.difference(fixed)
    if not _groups_can_consume(occupation.choice_groups, remaining):
        raise ValueError("本职技能没有满足职业模板中的组选要求")
    return tuple(sorted(selected_set))
