# -*- coding: utf-8 -*-
"""KP Agent 工具：把规则引擎暴露为 LLM 可调用的函数（function calling）。

工具全部确定性实现，由规则引擎保证正确性；LLM 只负责决定调用哪个工具、
传什么参数，然后依据返回结果进行叙述。
"""
from __future__ import annotations

import json
import random
from typing import Any, Callable

from ..character import create_character
from ..dice import Difficulty
from ..rules.checks import (
    luck_check, opposed_check, sanity_check, skill_check,
)
from ..rules.combat import Combatant, Weapon, resolve_attack
from ..rules.insanity import InsanityTracker
from ..retrieval import Index, search_rules
from ..skills import SkillCatalog, get_skill_catalog
from .state import Session
from .tool_schemas import TOOLS_SCHEMA

_DIFF = {
    "regular": Difficulty.REGULAR,
    "hard": Difficulty.HARD,
    "extreme": Difficulty.EXTREME,
}

# 属性中文名 -> 英文键
_ATTR_CN = {
    "力量": "STR", "体质": "CON", "敏捷": "DEX", "外貌": "APP",
    "意志": "POW", "意志力": "POW", "体型": "SIZ", "智力": "INT",
    "教育": "EDU", "幸运": "LUCK",
}
_ATTR_EN = ("STR", "CON", "DEX", "APP", "POW", "SIZ", "INT", "EDU", "LUCK")


def resolve_value(session: Session, ref: str, catalog: SkillCatalog | None = None) -> tuple[str, int]:
    """把技能/属性引用解析为 (名称, 数值)。支持数字、属性、别名与子技能。"""
    if ref is None:
        raise ValueError("缺少技能/属性名")
    s = str(ref).strip()
    if s.isdigit():
        return s, int(s)
    up = s.upper()
    if up in _ATTR_EN:
        key = up
        val = session.investigator.luck if key == "LUCK" else getattr(session.investigator.attributes, key)
        return key, val
    if s in _ATTR_CN:
        key = _ATTR_CN[s]
        val = session.investigator.luck if key == "LUCK" else getattr(session.investigator.attributes, key)
        return key, val
    skills = session.investigator.skills
    if s in skills:
        return s, skills[s]
    catalog = catalog or get_skill_catalog()
    canonical = catalog.canonicalize(s)
    if canonical in skills:
        return canonical, skills[canonical]
    for name in skills:  # 模糊匹配（包含关系）
        if s in name or name in s or canonical in name or name in canonical:
            return name, skills[name]
    raise ValueError(f"未找到技能/属性: {s!r}")


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def make_dispatcher(
    session: Session,
    *,
    rule_index: Index | None = None,
    tracer: Any = None,
    rng: random.Random | None = None,
    skill_catalog: SkillCatalog | None = None,
) -> Callable[[str, Any], dict]:
    """返回 dispatch(tool_name, arguments) -> dict。arguments 为 dict 或 JSON 字符串。"""
    rng = rng or random
    catalog = skill_catalog or get_skill_catalog()

    def _create_character(name: str = "调查员", age: int = 30) -> dict:
        c = create_character(name=name, age=age, rng=rng)
        session.investigator = c
        session.insanity = InsanityTracker()
        return {"message": f"已创建调查员「{name}」", "character": c.to_dict()}

    def _get_character() -> dict:
        return session.investigator.to_dict()

    def _roll_skill_check(
        skill: str,
        difficulty: str = "regular",
        bonus_dice: int = 0,
        penalty_dice: int = 0,
    ) -> dict:
        try:
            label, value = resolve_value(session, skill, catalog)
        except ValueError as exc:
            return {
                "error": str(exc),
                "candidates": catalog.resolve_action(
                    str(skill), session.investigator.skills, limit=3,
                ),
            }
        r = skill_check(value, _DIFF.get(difficulty, Difficulty.REGULAR), int(bonus_dice), int(penalty_dice), rng)
        return {
            "检定项": label, "数值": value, "难度": difficulty,
            "目标值": r.target, "掷骰": r.roll, "结果": r.degree_name,
            "自然成功度": r.degree_name, "行动结果": "成功" if r.success else "失败",
            "成功": r.success,
        }

    def _resolve_skill(action: str, limit: int = 3) -> dict:
        candidates = catalog.resolve_action(
            action, session.investigator.skills, limit=max(1, min(int(limit), 5)),
        )
        return {
            "action": action,
            "candidates": candidates,
            "note": "这些只是候选；由 KP 根据玩家意图、方法和情境选择最终技能。",
        }

    def _search_skills(query: str, category: str | None = None, limit: int = 5) -> dict:
        hits = catalog.search(query, category=category, limit=max(1, min(int(limit), 10)))
        return {
            "query": query,
            "skills": [
                {
                    **card.to_dict(),
                    "value": session.investigator.skills.get(card.canonical_name),
                }
                for card, _score in hits
            ],
            "message": "未找到匹配技能" if not hits else f"找到 {len(hits)} 条技能",
        }

    def _get_skill(name: str, section: str | None = None) -> dict:
        card = catalog.get(name)
        if card is None:
            return {
                "error": f"未找到技能: {name}",
                "candidates": catalog.resolve_action(name, session.investigator.skills),
            }
        payload = card.to_dict(detail=True)
        payload["value"] = session.investigator.skills.get(card.canonical_name)
        if section:
            selected = card.sections.get(str(section))
            payload["selected_section"] = selected if selected is not None else ""
        return payload

    def _opposed_check(skill: str, opponent_value: int) -> dict:
        label, value = resolve_value(session, skill)
        r = opposed_check(value, int(opponent_value), rng=rng)
        winner_cn = {"a": "我方", "b": "对方", "tie": "平手"}[r.winner]
        return {
            "我方检定项": label, "我方数值": value, "我方掷骰": r.roll_a, "我方结果": r.degree_a_name,
            "对方数值": r.value_b, "对方掷骰": r.roll_b, "对方结果": r.degree_b_name,
            "胜者": winner_cn,
        }

    def _luck_check() -> dict:
        r = luck_check(session.investigator.luck, rng=rng)
        return {
            "当前幸运": session.investigator.luck, "掷骰": r.roll,
            "结果": r.degree_name, "成功": r.success,
        }

    def _sanity_check(loss_success: str, loss_failure: str) -> dict:
        c = session.investigator
        before = c.san
        r = sanity_check(c.san, loss_success, loss_failure, rng=rng)
        c.san = r.san_after
        event = session.insanity.record_loss(r.loss, before, c.attributes.INT, rng=rng)
        out = {
            "掷骰": r.roll, "结果": r.degree_name, "成功": r.success,
            "损失理智": r.loss, "当前理智": c.san, "疯狂状态": event.state_after.value,
        }
        if r.needs_temporary_check:
            out["提示"] = "单次损失 ≥5 点，需进行 INT 检定判定临时性疯狂"
        return out

    def _update_character(
        delta_hp: int = 0, delta_mp: int = 0, delta_san: int = 0, delta_luck: int = 0,
    ) -> dict:
        c = session.investigator
        hp = _clamp(c.hp + int(delta_hp), 0, c.hp_max)
        mp = _clamp(c.mp + int(delta_mp), 0, c.mp_max)
        san = _clamp(c.san + int(delta_san), 0, 99)
        luck = _clamp(c.luck + int(delta_luck), 0, 99)
        c.hp, c.mp, c.san, c.luck = hp, mp, san, luck
        return {
            "HP": f"{c.hp}/{c.hp_max}", "MP": f"{c.mp}/{c.mp_max}",
            "SAN": f"{c.san}/{c.san_max}", "LUCK": c.luck,
        }

    def _set_skill(skill: str, value: int) -> dict:
        sheet = session.investigator
        name = catalog.canonicalize(skill) or str(skill).strip()
        value = _clamp(int(value), 0, 100)
        sheet.skills[name] = value
        return {"调查员": sheet.name, "技能": name, "数值": value}

    def _search_rules(query: str, limit: int = 3, type: str | None = None) -> dict:
        try:
            hits = search_rules(
                query, top_k=max(1, min(int(limit), 10)), type=type, index=rule_index,
            )
        except FileNotFoundError as exc:
            return {"query": query, "hits": [], "message": str(exc)}
        return {
            "query": query,
            "hits": [hit.to_dict() for hit in hits],
            "message": "未加载规则书或未命中" if not hits else f"命中 {len(hits)} 条规则",
        }

    def _module_status() -> dict:
        if session.module is None:
            return {"loaded": False, "message": "当前未加载模组"}
        return {"loaded": True, **session.module.status(player_safe=False)}

    def _search_module(query: str = "", limit: int = 3) -> dict:
        if session.module is None:
            raise ValueError("当前未加载模组")
        return session.module.keeper_context(query, limit=max(1, min(int(limit), 5)))

    def _advance_module(
        reason: str,
        completed_objectives: list[str] | None = None,
        next_node_id: str | None = None,
    ) -> dict:
        if session.module is None:
            raise ValueError("当前未加载模组")
        result = session.module.advance(reason, completed_objectives, next_node_id)
        session.log("推进模组场景", reason=reason, scene=result["scene"])
        return result

    def _combat_attack(
        skill: str,
        target_name: str,
        target_hp: int,
        target_hp_max: int,
        damage: str,
        target_armor: int = 0,
        weapon_name: str = "武器",
        difficulty: str = "regular",
    ) -> dict:
        label, value = resolve_value(session, skill)
        c = session.investigator
        attacker = Combatant(c.name, c.hp, c.hp_max, c.attributes.DEX, db=c.db, build=c.build)
        defender = Combatant(target_name, int(target_hp), int(target_hp_max), armor=int(target_armor))
        result = resolve_attack(
            attacker, defender, value, Weapon(weapon_name, damage, label),
            difficulty=_DIFF.get(difficulty, Difficulty.REGULAR), rng=rng,
        )
        payload = {
            "命中": result.hit,
            "攻击检定": result.attack.roll,
            "攻击结果": result.attack.degree_name,
            "目标": target_name,
        }
        if result.damage:
            payload.update({
                "原始伤害": result.damage.rolled, "护甲": result.damage.armor,
                "实际伤害": result.damage.damage, "目标HP": result.damage.hp_after,
                "重伤": result.damage.major_wound, "失去意识": result.damage.unconscious,
                "濒死": result.damage.dead,
            })
        return payload

    handlers = {
        "create_character": _create_character,
        "get_character": _get_character,
        "roll_skill_check": _roll_skill_check,
        "opposed_check": _opposed_check,
        "luck_check": _luck_check,
        "sanity_check": _sanity_check,
        "update_character": _update_character,
        "set_skill": _set_skill,
        "search_rules": _search_rules,
        "resolve_skill": _resolve_skill,
        "search_skills": _search_skills,
        "get_skill": _get_skill,
        "module_status": _module_status,
        "search_module": _search_module,
        "advance_module": _advance_module,
        "combat_attack": _combat_attack,
    }

    def dispatch(name: str, arguments: Any) -> dict:
        if name not in handlers:
            return {"error": f"未知工具: {name!r}"}
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if args is None:
                args = {}
            if not isinstance(args, dict):
                return {"error": "工具参数必须是 JSON 对象"}
            result = handlers[name](**args)
            if tracer is not None:
                tracer.record_tool(name, args, result)
            return result
        except Exception as e:  # noqa: BLE001 —— 任何错误都反馈给模型，便于其纠正
            return {"error": f"工具调用失败: {type(e).__name__}: {e}"}

    return dispatch
