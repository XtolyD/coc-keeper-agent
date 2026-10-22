# -*- coding: utf-8 -*-
"""本地属性块抽取（纯函数，不依赖 LLM）。"""
from __future__ import annotations

import re

from ..modules import ModuleActor


def _int_list(value) -> list[int]:
    result: list[int] = []
    for item in value or []:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def infer_title(page_text: list[str], fallback: str) -> str:
    """从首页第一行推断模组标题。"""
    if not page_text:
        return fallback
    for line in page_text[0].splitlines():
        candidate = line.strip()
        if 2 <= len(candidate) <= 80:
            return candidate
    return fallback


def merge_local_actors(actor_sets: list[list[ModuleActor]]) -> list[ModuleActor]:
    """合并多份本地抽取结果，复核稿优先。"""
    merged: list[ModuleActor] = []
    by_name: dict[str, ModuleActor] = {}
    for actors in actor_sets:
        for actor in actors:
            key = actor.name.strip().lower()
            if not key or re.search(r"\d|%|技能|攻击方式", actor.name):
                continue
            if key in by_name:
                current = by_name[key]
                current.attributes = {**actor.attributes, **current.attributes}
                current.skills = {**actor.skills, **current.skills}
                if not current.attacks:
                    current.attacks = actor.attacks
                current.armor = current.armor or actor.armor
                current.sanity_loss = current.sanity_loss or actor.sanity_loss
                current.source_pages = _int_list(current.source_pages + actor.source_pages)
                continue
            actor.id = f"actor-{len(merged) + 1:03d}"
            by_name[key] = actor
            merged.append(actor)
    return merged


def extract_stat_blocks(page_text: list[str]) -> list[ModuleActor]:
    """保守抽取 CoC 属性块；语义分析阶段会进一步细化。"""
    actors: list[ModuleActor] = []
    seen_names: set[str] = set()
    stat_pattern = re.compile(
        r"STR\s*(\d+)\s+CON\s*(\d+)\s+SIZ\s*(\d+)\s+DEX\s*(\d+)\s+INT\s*(\d+)\s+"
        r"APP\s*(\d+)\s+POW\s*(\d+)\s+EDU\s*(\d+)\s+SAN\s*([\d*]+)\s+HP\s*(\d+)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    skill_pattern = re.compile(r"([\u4e00-\u9fffA-Za-z/.（）()·]+)\s*(\d+)%")
    for page_number, text in enumerate(page_text, 1):
        for match in stat_pattern.finditer(text):
            raw_preceding = [line.strip() for line in text[max(0, match.start() - 240):match.start()].splitlines()]
            preceding = [line.strip(" ，,\t") for line in raw_preceding]
            candidates = [
                line for line in preceding if 1 < len(line) <= 50 and not re.match(r"^\d+\s*岁", line)
                and not re.search(r"角色与怪物|攻击方式|技能$", line)
            ]
            named_lines = [
                line.strip(" ，,\t") for line in raw_preceding
                if line.rstrip().endswith(("，", ",")) and 1 < len(line.strip(" ，,\t")) <= 50
            ]
            name = named_lines[-1] if named_lines else candidates[-1] if candidates else f"未命名角色-{len(actors) + 1}"
            if name in seen_names:
                continue
            seen_names.add(name)
            values = match.groups()
            attributes: dict[str, int | str] = dict(zip(
                ("STR", "CON", "SIZ", "DEX", "INT", "APP", "POW", "EDU"),
                (int(value) for value in values[:8]), strict=True,
            ))
            attributes["SAN"] = values[8]
            attributes["HP"] = int(values[9])
            tail = text[match.end():match.end() + 1800]
            skills = {skill: int(value) for skill, value in skill_pattern.findall(tail)}
            actors.append(ModuleActor(
                id=f"actor-{len(actors) + 1:03d}", name=name, attributes=attributes,
                skills=skills, source_pages=[page_number],
            ))

    combined = "\n".join(
        f"===== 第 {page_number} 页 =====\n{text}"
        for page_number, text in enumerate(page_text, 1)
    )
    header_pattern = re.compile(r"(?m)^([^\n，,。！？；：]{2,20})[，,]\s*\n([^\n。！？；：]{2,40})$")
    for match in header_pattern.finditer(combined):
        name = match.group(1).strip()
        if name in seen_names:
            continue
        block = combined[match.end():match.end() + 12_000]
        if "攻击方式" not in block or not ("护甲" in block or "理智损失" in block):
            continue
        attacks = [
            {"name": attack.strip(), "value": int(value), "damage": damage.strip()}
            for attack, value, damage in re.findall(
                r"(?m)^([^\n]{1,40}?)\s+(\d+)%[^\n]*?伤害\s*([^\n]+)", block,
            )
        ]
        armor_match = re.search(r"护甲[：:]\s*([^\n]+)", block)
        sanity_match = re.search(r"理智损失[：:]\s*([^\n]+)", block)
        pages = _int_list(re.findall(r"=====\s*第\s*(\d+)\s*页\s*=====", block))
        if not pages:
            markers = re.findall(r"=====\s*第\s*(\d+)\s*页\s*=====", combined[:match.start()])
            pages = [int(markers[-1])] if markers else []
        seen_names.add(name)
        actors.append(ModuleActor(
            id=f"actor-{len(actors) + 1:03d}", name=name, kind="monster",
            role=match.group(2).strip(), attacks=attacks,
            armor=armor_match.group(1).strip() if armor_match else "",
            sanity_loss=sanity_match.group(1).strip() if sanity_match else "",
            source_pages=pages,
        ))
    return actors
