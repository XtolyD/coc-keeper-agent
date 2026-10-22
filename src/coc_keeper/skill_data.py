# -*- coding: utf-8 -*-
"""技能基础数据：从 skills_core.json 派生 canonical 名称、别名与基础值。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
CORE_PATH = DATA_DIR / "skills_core.json"
PLAYBOOK_PATH = DATA_DIR / "skills_playbook.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CORE: dict[str, Any] = _load(CORE_PATH)
PLAYBOOK: dict[str, Any] = _load(PLAYBOOK_PATH)
SKILL_RECORDS: tuple[dict[str, Any], ...] = tuple(CORE.get("skills", []))


def clean_name(value: object) -> str:
    text = str(value or "").strip()
    return text.rstrip("：:").strip()


_CANONICAL_ALIASES: dict[str, str] = {}
for _record in SKILL_RECORDS:
    _name = clean_name(_record.get("name"))
    _canonical = clean_name(_record.get("canonical_name"))
    if not _name or not _canonical:
        continue
    _CANONICAL_ALIASES[_name] = _canonical
    for _alias in _record.get("aliases", []) or []:
        if _alias:
            _CANONICAL_ALIASES.setdefault(str(_alias).strip(), _canonical)
# 常见输入别名
_CANONICAL_ALIASES.update({
    "取悦": "魅惑",
    "电子学Ω": "电子学",
    "电子学 Ω": "电子学",
    "动物驯养": "驯兽",
    "艺术与手艺": "艺术/手艺",
    "技艺": "艺术/手艺",
    "射击": "射击（手枪）",
    "格斗": "格斗（斗殴）",
    "驾驶": "驾驶（飞行/航海）",
    "生存：": "生存",
    "学识：": "学识",
})


def canonicalize(name: object) -> str:
    """把技能名、别名或子技能解析为角色卡使用的 canonical 名称。"""
    text = clean_name(name)
    if not text:
        return ""
    if text in _CANONICAL_ALIASES:
        return _CANONICAL_ALIASES[text]
    lowered = text.casefold()
    for key, value in _CANONICAL_ALIASES.items():
        if key.casefold() == lowered:
            return value
    return text


def _base_spec(record: dict[str, Any]) -> dict[str, Any]:
    base = record.get("base") or {"kind": "none"}
    if not isinstance(base, dict):
        return {"kind": "none"}
    return base


_PREFERRED_BASE_NAME = {
    "格斗（斗殴）": "斗殴",
    "射击（手枪）": "手枪",
    "射击（步枪/霰弹枪）": "步枪/霰弹枪",
}


def _choose_best_base(records: list[dict[str, Any]], canonical: str) -> dict[str, Any]:
    preferred = _PREFERRED_BASE_NAME.get(canonical)
    if preferred:
        for record in records:
            if clean_name(record.get("name")) == preferred:
                return _base_spec(record)
    for record in records:
        if clean_name(record.get("name")) == canonical:
            spec = _base_spec(record)
            if spec.get("kind") != "none":
                return spec
    fixed = [r for r in records if _base_spec(r).get("kind") == "fixed"]
    if fixed:
        return _base_spec(fixed[0])
    dynamic = [r for r in records if _base_spec(r).get("kind") == "attribute"]
    if dynamic:
        return _base_spec(dynamic[0])
    return {"kind": "none"}


SKILL_CANONICAL_NAMES: list[str] = []
for _record in SKILL_RECORDS:
    _canonical = clean_name(_record.get("canonical_name"))
    if _canonical and _canonical not in SKILL_CANONICAL_NAMES:
        SKILL_CANONICAL_NAMES.append(_canonical)

SKILL_BASE_SPECS: dict[str, dict[str, Any]] = {}
for _canonical in SKILL_CANONICAL_NAMES:
    _matching = [
        r for r in SKILL_RECORDS
        if clean_name(r.get("canonical_name")) == _canonical
    ]
    SKILL_BASE_SPECS[_canonical] = _choose_best_base(_matching, _canonical)


def _static_base(spec: dict[str, Any]) -> int | None:
    kind = spec.get("kind")
    if kind == "fixed":
        try:
            return int(spec.get("value"))
        except (TypeError, ValueError):
            return 0
    if kind == "attribute":
        return None
    return 0


SKILL_BASES: dict[str, int | None] = {
    name: _static_base(spec) for name, spec in SKILL_BASE_SPECS.items()
}


def base_value(name: object, attributes: Any) -> int:
    """按 canonical 技能名计算基础值；attributes 需有 DEX/EDU 等属性。"""
    canonical = canonicalize(name)
    spec = SKILL_BASE_SPECS.get(canonical, {"kind": "none"})
    kind = spec.get("kind")
    if kind == "fixed":
        try:
            return int(spec.get("value"))
        except (TypeError, ValueError):
            return 0
    if kind == "attribute":
        attr = str(spec.get("attribute", "")).upper()
        factor = float(spec.get("factor", 1.0))
        try:
            raw = getattr(attributes, attr)
        except AttributeError:
            return 0
        return int(raw * factor)
    return 0


def base_skill_values(attributes: Any) -> dict[str, int]:
    return {name: base_value(name, attributes) for name in SKILL_BASES}
