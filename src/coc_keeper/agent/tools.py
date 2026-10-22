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
from ..retrieval import Index, search_rules
from .state import Session

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


def resolve_value(session: Session, ref: str) -> tuple[str, int]:
    """把技能/属性引用解析为 (名称, 数值)。支持数字、属性、技能名（含模糊匹配）。"""
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
    for name in skills:  # 模糊匹配（包含关系）
        if s in name or name in s:
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
) -> Callable[[str, Any], dict]:
    """返回 dispatch(tool_name, arguments) -> dict。arguments 为 dict 或 JSON 字符串。"""
    rng = rng or random

    def _create_character(name: str = "调查员", age: int = 30) -> dict:
        c = create_character(name=name, age=age, rng=rng)
        if len(session.players) == 1 and session.investigator.name in session.players:
            session.players.pop(session.investigator.name, None)
            session.investigator = c
        session.add_player(c)
        return {"message": f"已创建调查员「{name}」", "character": c.to_dict()}

    def _get_character(name: str | None = None) -> dict:
        return session.get_player(name).to_dict()

    def _roll_skill_check(
        skill: str,
        difficulty: str = "regular",
        bonus_dice: int = 0,
        penalty_dice: int = 0,
    ) -> dict:
        label, value = resolve_value(session, skill)
        r = skill_check(value, _DIFF.get(difficulty, Difficulty.REGULAR), int(bonus_dice), int(penalty_dice), rng)
        return {
            "检定项": label, "数值": value, "难度": difficulty,
            "目标值": r.target, "掷骰": r.roll, "结果": r.degree_name,
            "成功": r.success,
        }

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
        c.hp = _clamp(c.hp + int(delta_hp), 0, c.hp_max)
        c.mp = _clamp(c.mp + int(delta_mp), 0, c.mp_max)
        c.san = _clamp(c.san + int(delta_san), 0, 99)
        c.luck = _clamp(c.luck + int(delta_luck), 0, 99)
        return {
            "HP": f"{c.hp}/{c.hp_max}", "MP": f"{c.mp}/{c.mp_max}",
            "SAN": f"{c.san}/{c.san_max}", "LUCK": c.luck,
        }

    def _add_player(name: str, age: int = 30) -> dict:
        if name in session.players:
            raise ValueError(f"玩家已存在: {name}")
        sheet = create_character(name=name, age=age, rng=rng)
        session.add_player(sheet)
        return {"message": f"已加入调查员「{name}」", "character": sheet.to_dict()}

    def _set_skill(skill: str, value: int, player_name: str | None = None) -> dict:
        sheet = session.get_player(player_name)
        value = _clamp(int(value), 0, 100)
        sheet.skills[str(skill).strip()] = value
        return {"调查员": sheet.name, "技能": str(skill).strip(), "数值": value}

    def _team_luck_check() -> dict:
        return {"团队幸运检定": session.team_luck_check(rng=rng)}

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
        "add_player": _add_player,
        "set_skill": _set_skill,
        "team_luck_check": _team_luck_check,
        "search_rules": _search_rules,
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


#: OpenAI function calling 的工具定义（schema）
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": "创建一名新调查员（随机掷属性，技能为基础值）。玩家要求重骰/建卡时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "调查员姓名"},
                    "age": {"type": "integer", "description": "年龄，默认30"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_character",
            "description": "读取当前调查员角色卡（属性/HP/MP/SAN/幸运/技能）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "roll_skill_check",
            "description": "掷一次技能/属性检定（d100）。判定调查员某个行动是否成功。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "技能名或属性名，如 侦查/聆听/闪避/格斗（斗殴）/STR/智力"},
                    "difficulty": {
                        "type": "string",
                        "enum": ["regular", "hard", "extreme"],
                        "description": "难度：regular常规 / hard困难(半值) / extreme极难(五分之一)",
                    },
                    "bonus_dice": {"type": "integer", "description": "奖励骰数量，默认0"},
                    "penalty_dice": {"type": "integer", "description": "惩罚骰数量，默认0"},
                },
                "required": ["skill"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "opposed_check",
            "description": "对抗检定（近战格斗、力量对抗等）。比较调查员与对方的成功度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "调查员使用的技能/属性名"},
                    "opponent_value": {"type": "integer", "description": "对方的技能/属性值"},
                },
                "required": ["skill", "opponent_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "luck_check",
            "description": "幸运检定：d100 ≤ 当前幸运值即成功。用于命运/巧合类判定。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sanity_check",
            "description": "理智检定：d100 ≤ 当前理智即成功，失败/大失败损失理智并落地数值。",
            "parameters": {
                "type": "object",
                "properties": {
                    "loss_success": {"type": "string", "description": "成功时损失，如 0"},
                    "loss_failure": {"type": "string", "description": "失败时损失，如 1d6"},
                },
                "required": ["loss_success", "loss_failure"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_character",
            "description": "增减调查员状态（HP/MP/SAN/幸运），用正负增量。例如受伤 delta_hp=-3。",
            "parameters": {
                "type": "object",
                "properties": {
                    "delta_hp": {"type": "integer", "description": "HP 变化量（负为受伤）"},
                    "delta_mp": {"type": "integer", "description": "MP 变化量"},
                    "delta_san": {"type": "integer", "description": "SAN 变化量"},
                    "delta_luck": {"type": "integer", "description": "幸运变化量"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_player",
            "description": "向当前战役加入一名调查员。多人跑团开场时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "调查员姓名"},
                    "age": {"type": "integer", "description": "年龄，默认30"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_skill",
            "description": "设置指定调查员的技能值，用于建卡或技能成长。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "技能名称"},
                    "value": {"type": "integer", "description": "新的技能值，0到100"},
                    "player_name": {"type": "string", "description": "调查员姓名；省略为主调查员"},
                },
                "required": ["skill", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_luck_check",
            "description": "对队伍中所有调查员分别进行幸运检定。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rules",
            "description": "检索 CoC 7th 规则书并返回带页码的原文。对规则不确定时必须使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "规则问题或关键词"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认3"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "module_status",
            "description": "查看当前模组和当前场景的 Keeper 专用进度，不向玩家展示返回原文。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_module",
            "description": "只检索当前场景的模组原文。未来场景不会被返回；不得向玩家逐字复述 Keeper 资料。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "当前行动涉及的人物、地点或线索"},
                    "limit": {"type": "integer", "description": "最多返回片段数，默认3"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "advance_module",
            "description": "当前场景目标完成后，依据玩家行动沿剧情图推进。不得选择当前不可用的分支。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "玩家已完成的、足以推进场景的游戏内事件"},
                    "completed_objectives": {
                        "type": "array", "items": {"type": "string"},
                        "description": "已完成目标，必须与当前场景清单逐项一致",
                    },
                    "next_node_id": {
                        "type": "string",
                        "description": "存在多个剧情分支时，从 search_module 的 available_branches 选择目标节点 ID",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "combat_attack",
            "description": "执行一次攻击检定并结算武器伤害、护甲、重伤和失去意识。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "使用的战斗技能"},
                    "target_name": {"type": "string", "description": "目标名称"},
                    "target_hp": {"type": "integer", "description": "目标当前HP"},
                    "target_hp_max": {"type": "integer", "description": "目标最大HP"},
                    "damage": {"type": "string", "description": "武器伤害表达式，如1d6"},
                    "target_armor": {"type": "integer", "description": "目标护甲"},
                    "weapon_name": {"type": "string", "description": "武器名称"},
                    "difficulty": {"type": "string", "enum": ["regular", "hard", "extreme"]},
                },
                "required": ["skill", "target_name", "target_hp", "target_hp_max", "damage"],
            },
        },
    },
]
