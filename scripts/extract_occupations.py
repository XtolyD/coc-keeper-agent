# -*- coding: utf-8 -*-
"""从 COC7 Excel 角色卡提取职业建卡规则。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from openpyxl import load_workbook


MARKERS = (("☆", 3), ("⊙", 4), ("☯", 5), ("※", 6))
SKILL_ALIASES = {
    "取悦": "魅惑",
    "计算机使用 Ω": "计算机使用",
    "电子学 Ω": "电子学",
    "技艺①": "艺术/手艺",
    "技艺②": "艺术/手艺",
    "技艺③": "艺术/手艺",
    "格斗：": "格斗（斗殴）",
    "格斗①": "格斗（斗殴）",
    "格斗②": "格斗（斗殴）",
    "格斗③": "格斗（斗殴）",
    "射击：": "射击（手枪）",
    "射击①": "射击（手枪）",
    "射击②": "射击（手枪）",
    "射击③": "射击（手枪）",
    "外语①": "外语",
    "外语②": "外语",
    "外语③": "外语",
    "驾驶：": "驾驶（飞行/航海）",
    "科学①": "科学",
    "科学②": "科学",
    "科学③": "科学",
    "生存：": "生存",
    "学识：": "学识",
}


def canonical_skill(value: object) -> str | None:
    name = str(value or "").strip()
    if not name or name in {"0", "自定义技能"}:
        return None
    return SKILL_ALIASES.get(name, name)


def parse_credit(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[-—]\s*(\d+)\s*", str(value or ""))
    if not match:
        raise ValueError(f"无法解析信用评级范围: {value!r}")
    return int(match.group(1)), int(match.group(2))


def extract(source: Path) -> list[dict]:
    workbook = load_workbook(source, data_only=False, read_only=False)
    occupations = workbook["职业列表"]
    matrix = workbook["本职技能"]
    columns = {
        int(matrix.cell(1, column).value): column
        for column in range(2, matrix.max_column + 1)
        if isinstance(matrix.cell(1, column).value, int)
    }
    rows = {
        row: canonical_skill(matrix.cell(row, 1).value)
        for row in range(8, 74)
    }
    output: list[dict] = []
    for row in range(4, 234):
        occupation_id = occupations[f"A{row}"].value
        if not isinstance(occupation_id, int) or occupation_id not in columns:
            continue
        column = columns[occupation_id]
        fixed = {"信用评级"}
        groups: list[dict] = []
        free_choices = int(matrix.cell(7, column).value or 0)
        for skill_row, skill_name in rows.items():
            if not skill_name:
                continue
            value = matrix.cell(skill_row, column).value
            if value == "★" or (value not in (None, "") and value not in {marker for marker, _ in MARKERS}):
                fixed.add(skill_name)
        for marker, count_row in MARKERS:
            count = matrix.cell(count_row, column).value
            if not isinstance(count, (int, float)) or count <= 0:
                continue
            allowed = sorted({
                skill_name for skill_row, skill_name in rows.items()
                if skill_name and matrix.cell(skill_row, column).value == marker
            })
            if allowed:
                groups.append({"count": int(count), "skills": allowed})
            else:
                free_choices += int(count)
        credit_min, credit_max = parse_credit(occupations[f"D{row}"].value)
        formula = str(occupations[f"F{row}"].value).lstrip("=")
        output.append({
            "id": occupation_id,
            "name": str(occupations[f"B{row}"].value),
            "credit_min": credit_min,
            "credit_max": credit_max,
            "point_formula": formula,
            "point_formula_label": str(occupations[f"E{row}"].value),
            "skill_template": str(occupations[f"G{row}"].value),
            "fixed_skills": sorted(fixed),
            "choice_groups": groups,
            "free_choice_count": free_choices,
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "coc_keeper" / "data" / "occupations.json",
    )
    args = parser.parse_args()
    payload = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(payload)} occupations to {args.output}")


if __name__ == "__main__":
    main()
