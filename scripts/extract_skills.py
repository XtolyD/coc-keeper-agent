# -*- coding: utf-8 -*-
"""从 COC7 角色卡 xlsx 的「附表」生成 skills_core.json。

用法：
    python scripts/extract_skills.py
    python scripts/extract_skills.py --source data/COC7空白卡.xlsx \
        --output src/coc_keeper/data/skills_core.json

只生成“事实与原文”；技能的使用语义（use_when/alternatives）在
skills_playbook.json 中人工维护，避免重新生成时被覆盖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "COC7空白卡.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "src" / "coc_keeper" / "data" / "skills_core.json"

# 子技能 → 角色卡现有 canonical 技能名（保持建卡/旧角色卡兼容）
CANONICAL = {
    "取悦": "魅惑",
    "电子学 Ω": "电子学",
    "动物驯养": "驯兽",
    "技艺①": "艺术/手艺",
    "技艺②": "艺术/手艺",
    "技艺③": "艺术/手艺",
    "格斗①": "格斗（斗殴）",
    "格斗②": "格斗（斗殴）",
    "格斗③": "格斗（斗殴）",
    "射击①": "射击（手枪）",
    "射击②": "射击（步枪/霰弹枪）",
    "射击③": "射击（手枪）",
    "外语①": "外语",
    "外语②": "外语",
    "外语③": "外语",
    "科学①": "科学",
    "科学②": "科学",
    "科学③": "科学",
    "生存：": "生存",
    "学识：": "学识",
}

PARENT_NAMES = {
    "艺术与手艺": "艺术/手艺",
    "格斗": "格斗（斗殴）",
    "射击": "射击（手枪）",
    "科学": "科学",
    "外语": "外语",
    "驾驶": "驾驶（飞行/航海）",
    "生存：": "生存",
    "学识：": "学识",
}

FIGHTING_FALLBACK = "格斗（斗殴）"
FIREARM_FALLBACK = "射击（步枪/霰弹枪）"

CATEGORY = {
    "会计": "investigation", "人类学": "investigation", "估价": "investigation",
    "考古学": "investigation", "侦查": "investigation", "聆听": "investigation",
    "图书馆使用": "investigation", "博物学": "investigation", "导航": "investigation",
    "神秘学": "investigation", "追踪": "investigation",
    "魅惑": "social", "话术": "social", "恐吓": "social", "说服": "social",
    "心理学": "social",
    "格斗（斗殴）": "combat", "射击（手枪）": "combat",
    "射击（步枪/霰弹枪）": "combat", "闪避": "combat", "投掷": "combat",
    "炮术": "combat", "爆破": "combat",
    "攀爬": "physical", "跳跃": "physical", "游泳": "physical",
    "潜行": "physical", "骑术": "physical", "潜水": "physical",
    "锁匠": "technical", "机械维修": "technical", "电气维修": "technical",
    "电子学": "technical", "计算机使用": "technical", "汽车驾驶": "technical",
    "驾驶（飞行/航海）": "technical", "操作重型机械": "technical",
    "历史": "knowledge", "法律": "knowledge", "医学": "knowledge",
    "科学": "knowledge", "外语": "knowledge", "母语": "knowledge",
    "精神分析": "knowledge", "学识": "knowledge", "急救": "medical",
    "艺术/手艺": "art", "信用评级": "social", "克苏鲁神话": "knowledge",
}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _base(value: str) -> dict:
    value = value.strip()
    if not value or value == "——":
        return {"kind": "none"}
    if value in {"DEX一半的%", "DEX一半%"}:
        return {"kind": "attribute", "attribute": "DEX", "factor": 0.5}
    if value in {"EDU%", "EDU"}:
        return {"kind": "attribute", "attribute": "EDU", "factor": 1.0}
    match = re.fullmatch(r"(\d+)%?", value)
    if match:
        return {"kind": "fixed", "value": int(match.group(1))}
    return {"kind": "text", "value": value}


def _parent(name: str, special: str) -> tuple[str | None, str | None]:
    if "技艺的子项" in special:
        return "艺术与手艺", "艺术/手艺"
    if "格斗的子项" in special:
        return "格斗", FIGHTING_FALLBACK
    if "射击的子项" in special:
        canonical = {
            "手枪": "射击（手枪）",
            "步枪/霰弹枪": "射击（步枪/霰弹枪）",
        }.get(name, FIREARM_FALLBACK)
        return "射击", canonical
    if "科学的子项" in special:
        return "科学", "科学"
    if name in PARENT_NAMES:
        return name, PARENT_NAMES[name]
    return None, CANONICAL.get(name, name)


def extract(source: Path) -> dict:
    workbook = load_workbook(source, data_only=True, read_only=False)
    sheet = workbook["附表"]
    skills = []
    for row in range(95, 213):
        name = _text(sheet.cell(row=row, column=2).value)
        if not name or set(name) <= {"—", "-", "－"}:
            continue
        base_raw = _text(sheet.cell(row=row, column=3).value)
        special = _text(sheet.cell(row=row, column=4).value)
        if name == "0" or special == "自定义技能":
            continue
        parent, canonical = _parent(name, special)
        canonical = CANONICAL.get(name, canonical)
        item = {
            "id": f"skill.{row}",
            "name": name,
            "canonical_name": canonical,
            "aliases": sorted({
                alias for alias, target in CANONICAL.items()
                if target == canonical and alias != name
            }),
            "parent_name": parent,
            "specialization": bool(parent and parent != name),
            "category": CATEGORY.get(canonical, "other"),
            "base": _base(base_raw),
            "source": {"sheet": "附表", "range": f"B{row}:K{row}"},
            "sections": {
                "special_applicability": _text(sheet.cell(row=row, column=4).value),
                "difficulty_depends_on": _text(sheet.cell(row=row, column=5).value),
                "description": _text(sheet.cell(row=row, column=6).value),
                "normal_difficulty": _text(sheet.cell(row=row, column=7).value),
                "hard_difficulty": _text(sheet.cell(row=row, column=8).value),
                "push_examples": _text(sheet.cell(row=row, column=9).value),
                "push_failure": _text(sheet.cell(row=row, column=10).value),
                "insane_failure": _text(sheet.cell(row=row, column=11).value),
            },
        }
        skills.append(item)
    if len(skills) < 100:
        raise ValueError(f"技能数量异常: {len(skills)}")
    return {
        "schema_version": 1,
        "source": str(source.name),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_sheet": "附表!B95:K212",
        "count": len(skills),
        "skills": skills,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"源文件不存在: {args.source}")
    payload = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {payload['count']} skills to {args.output}")


if __name__ == "__main__":
    main()
