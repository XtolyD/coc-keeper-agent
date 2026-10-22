# -*- coding: utf-8 -*-
"""技能目录：事实数据、别名解析、行动候选与可解释检索。

设计：
- 事实来自 skills_core.json（xlsx 生成）；使用语义来自 skills_playbook.json（人工维护）。
- 精确名称/别名优先，BM25 只用于模糊检索。
- resolve_action 只给 KP 提供候选，最终用哪个技能由 Agent 决定。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from .retrieval import Index, search
from .skill_data import CORE, PLAYBOOK, SKILL_BASE_SPECS, base_value, canonicalize, clean_name


def _text(value: object) -> str:
    return str(value or "").strip()


def _sentence(text: str, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    match = re.split(r"[。；;!?！？]", text, maxsplit=1)
    return (match[0][:limit] if match else text[:limit]).strip()


@dataclass(frozen=True)
class SkillCard:
    id: str
    name: str
    canonical_name: str
    aliases: tuple[str, ...]
    category: str
    base: dict[str, Any]
    parent_name: str | None
    specialization: bool
    source: dict[str, Any]
    sections: dict[str, str]
    playbook: dict[str, Any]

    @property
    def use_when(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.playbook.get("use_when", []))

    @property
    def avoid_when(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.playbook.get("avoid_when", []))

    @property
    def triggers(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.playbook.get("triggers", []))

    @property
    def alternatives(self) -> tuple[dict[str, str], ...]:
        items = self.playbook.get("alternatives", [])
        return tuple(
            {"skill": str(item.get("skill", "")), "difference": str(item.get("difference", ""))}
            for item in items if isinstance(item, dict)
        )

    def base_for(self, attributes: Any) -> int:
        return base_value(self.canonical_name, attributes)

    def summary(self, limit: int = 180) -> str:
        if self.use_when:
            return _sentence(self.use_when[0], limit)
        return _sentence(self.sections.get("description", ""), limit)

    def to_dict(self, *, detail: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "category": self.category,
            "base": dict(self.base),
            "parent_name": self.parent_name,
            "specialization": self.specialization,
            "summary": self.summary(),
            "use_when": list(self.use_when),
            "avoid_when": list(self.avoid_when),
            "alternatives": list(self.alternatives),
            "check_type": self.playbook.get("check_type", "regular"),
            "failure_style": self.playbook.get("failure_style", ""),
            "source": dict(self.source),
        }
        if detail:
            payload["sections"] = dict(self.sections)
            payload["related_skills"] = list(self.playbook.get("related_skills", []))
        return payload


class SkillCatalog:
    def __init__(self) -> None:
        self._records = [dict(item) for item in CORE.get("skills", [])]
        self._playbook = dict(PLAYBOOK.get("skills", {}))
        self._by_name: dict[str, SkillCard] = {}
        self._by_canonical: dict[str, SkillCard] = {}
        self._cards: list[SkillCard] = []
        for record in self._records:
            name = clean_name(record.get("name"))
            canonical = canonicalize(record.get("canonical_name") or name)
            if not name or not canonical:
                continue
            card = SkillCard(
                id=_text(record.get("id")) or f"skill.{len(self._cards)}",
                name=name,
                canonical_name=canonical,
                aliases=tuple(str(item) for item in record.get("aliases", []) if item),
                category=_text(record.get("category")) or "other",
                base=dict(SKILL_BASE_SPECS.get(canonical) or record.get("base") or {"kind": "none"}),
                parent_name=record.get("parent_name"),
                specialization=bool(record.get("specialization")),
                source=dict(record.get("source") or {}),
                sections={str(k): str(v) for k, v in dict(record.get("sections") or {}).items()},
                playbook=dict(self._playbook.get(canonical) or self._playbook.get(name) or {}),
            )
            self._cards.append(card)
            self._by_name.setdefault(name.casefold(), card)
            self._by_name.setdefault(canonical.casefold(), card)
            self._by_canonical.setdefault(canonical.casefold(), card)
        # canonical 代表：优先人工指定的子技能，其次与 canonical 同名的条目。
        preferred = {
            "格斗（斗殴）": "斗殴",
            "射击（手枪）": "手枪",
            "射击（步枪/霰弹枪）": "步枪/霰弹枪",
            "魅惑": "取悦",
            "电子学": "电子学 Ω",
            "驯兽": "动物驯养",
            "驾驶（飞行/航海）": "驾驶",
            "生存": "生存：",
            "学识": "学识：",
            "艺术/手艺": "艺术与手艺",
            "科学": "科学",
            "外语": "外语",
        }
        for canonical_name, raw_name in preferred.items():
            card = self._by_name.get(raw_name.casefold())
            if card is not None:
                self._by_canonical[canonical_name.casefold()] = card
        for card in self._cards:
            key = card.canonical_name.casefold()
            if card.name == card.canonical_name:
                self._by_canonical[key] = card
        self._index: Index | None = None
        self._index_cards: list[SkillCard] = []

    def get(self, name: object) -> SkillCard | None:
        text = _text(name)
        if not text:
            return None
        canonical = canonicalize(text)
        return (
            self._by_name.get(text.casefold())
            or self._by_name.get(canonical.casefold())
            or self._by_canonical.get(canonical.casefold())
        )

    def canonicalize(self, name: object) -> str:
        return canonicalize(name)

    def categories(self) -> list[str]:
        return sorted({card.category for card in self._cards})

    def cards(self) -> list[SkillCard]:
        return list(self._cards)

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[tuple[SkillCard, float]]:
        text = _text(query)
        if not text:
            return []
        exact = self.get(text)
        results: list[tuple[SkillCard, float]] = []
        seen: set[str] = set()
        if exact is not None and (category is None or exact.category == category):
            results.append((exact, 1.0))
            seen.add(exact.id)
        if self._index is None:
            self._build_index()
        assert self._index is not None
        by_id = {card.id: card for card in self._index_cards}
        for hit in search(self._index, text, top_k=max(limit * 3, 8)):
            card = by_id.get(hit.path)
            if card is None or card.id in seen:
                continue
            if category is not None and card.category != category:
                continue
            results.append((card, float(hit.score)))
            seen.add(card.id)
            if len(results) >= limit:
                break
        return results[:limit]

    def resolve_action(
        self,
        action: str,
        character_skills: dict[str, int] | None = None,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """给出行动可能对应的技能候选；最终选择由 Agent/KP 决定。"""
        skills = {str(k): int(v) for k, v in (character_skills or {}).items()}
        text = _text(action)
        folded = text.casefold()
        # 先用人工维护的触发词精确匹配；命中时不再用泛化 BM25 拉入无关技能。
        matched: list[tuple[int, SkillCard]] = []
        for card in self._cards:
            for trigger in card.triggers:
                if trigger and trigger.casefold() in folded:
                    matched.append((len(trigger), card))
                    break
        if matched:
            matched.sort(key=lambda item: (-item[0], item[1].name))
            hits = [(card, 1.0) for _, card in matched]
            confidence = 0.95
        else:
            # 技能名/别名出现在行动文本里时优先；例如“我想说服守卫”。
            named = [
                card for card in self._cards
                if card.name.casefold() in folded
                or card.canonical_name.casefold() in folded
                or any(alias.casefold() in folded for alias in card.aliases)
            ]
            if named:
                named.sort(key=lambda card: -len(card.name))
                hits = [(card, 0.9) for card in named]
                confidence = 0.85
            else:
                # 没有触发词/名称命中时，不把泛化 BM25 结果硬塞给 KP；
                # Agent 可以自行判断，或调用 search_skills 做更明确的查询。
                return []
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for card, score in hits:
            if card.canonical_name in seen:
                continue
            seen.add(card.canonical_name)
            value = skills.get(card.canonical_name)
            if value is None:
                for raw_name, raw_value in skills.items():
                    if canonicalize(raw_name) == card.canonical_name:
                        value = raw_value
                        break
            candidates.append({
                "skill": card.canonical_name,
                "display_name": card.name,
                "value": value,
                "category": card.category,
                "confidence": round(max(0.3, confidence - 0.1 * len(candidates)), 2),
                "why": card.summary(),
                "use_when": list(card.use_when),
                "avoid_when": list(card.avoid_when),
                "alternatives": list(card.alternatives),
                "check_type": card.playbook.get("check_type", "regular"),
                "failure_style": card.playbook.get("failure_style", ""),
                "source": dict(card.source),
            })
            if len(candidates) >= limit:
                break
        return candidates

    def _build_index(self) -> None:
        chunks: list[dict[str, Any]] = []
        cards: list[SkillCard] = []
        for card in self._cards:
            name_field = " ".join([card.name, card.canonical_name, *card.aliases])
            text_field = " ".join([
                *card.use_when,
                *card.avoid_when,
                *[item.get("difference", "") for item in card.alternatives],
                card.sections.get("description", ""),
                card.sections.get("special_applicability", ""),
                card.sections.get("difficulty_depends_on", ""),
                card.playbook.get("failure_style", ""),
            ])
            row = int(card.source.get("row", 0) or 0)
            chunks.append({
                "type": "skill", "name": name_field, "text": text_field,
                "page": row, "start_page": row, "end_page": row,
                "path": card.id, "lines": [*card.use_when, card.sections.get("description", "")],
            })
            cards.append(card)
        self._index = Index.build(chunks)
        self._index_cards = cards


@lru_cache(maxsize=1)
def get_skill_catalog() -> SkillCatalog:
    return SkillCatalog()


def canonical_skill_name(name: object) -> str:
    return canonicalize(name)
