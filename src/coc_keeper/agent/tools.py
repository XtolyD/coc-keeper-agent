# -*- coding: utf-8 -*-
"""KP Agent 工具：把规则引擎暴露为 LLM 可调用的函数（function calling）。

工具全部确定性实现，由规则引擎保证正确性；LLM 只负责决定调用哪个工具、
传什么参数，然后依据返回结果进行叙述。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from ..character import create_character
from ..dice import Difficulty
from ..rules.checks import (
    luck_check, opposed_check, sanity_check, skill_check,
)
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


def make_dispatcher(session: Session) -> Callable[[str, Any], dict]:
    """返回 dispatch(tool_name, arguments) -> dict。arguments 为 dict 或 JSON 字符串。"""

    def _create_character(name: str = "调查员", age: int = 30) -> dict:
        c = create_character(name=name, age=age)
        session.investigator = c
        return {"message": f"已创建调查员「{name}」", "character": c.to_dict()}

    def _get_character() -> dict:
        return session.investigator.to_dict()

    def _roll_skill_check(
        skill: str,
        difficulty: str = "regular",
        bonus_dice: int = 0,
        penalty_dice: int = 0,
    ) -> dict:
        label, value = resolve_value(session, skill)
        r = skill_check(value, _DIFF.get(difficulty, Difficulty.REGULAR), int(bonus_dice), int(penalty_dice))
        return {
            "检定项": label, "数值": value, "难度": difficulty,
            "目标值": r.target, "掷骰": r.roll, "结果": r.degree_name,
            "成功": r.success,
        }

    def _opposed_check(skill: str, opponent_value: int) -> dict:
        label, value = resolve_value(session, skill)
        r = opposed_check(value, int(opponent_value))
        winner_cn = {"a": "我方", "b": "对方", "tie": "平手"}[r.winner]
        return {
            "我方检定项": label, "我方数值": value, "我方掷骰": r.roll_a, "我方结果": r.degree_a_name,
            "对方数值": r.value_b, "对方掷骰": r.roll_b, "对方结果": r.degree_b_name,
            "胜者": winner_cn,
        }

    def _luck_check() -> dict:
        r = luck_check(session.investigator.luck)
        return {
            "当前幸运": session.investigator.luck, "掷骰": r.roll,
            "结果": r.degree_name, "成功": r.success,
        }

    def _sanity_check(loss_success: str, loss_failure: str) -> dict:
        c = session.investigator
        r = sanity_check(c.san, loss_success, loss_failure)
        c.san = r.san_after
        out = {
            "掷骰": r.roll, "结果": r.degree_name, "成功": r.success,
            "损失理智": r.loss, "当前理智": c.san,
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

    handlers = {
        "create_character": _create_character,
        "get_character": _get_character,
        "roll_skill_check": _roll_skill_check,
        "opposed_check": _opposed_check,
        "luck_check": _luck_check,
        "sanity_check": _sanity_check,
        "update_character": _update_character,
    }

    def dispatch(name: str, arguments: Any) -> dict:
        if name not in handlers:
            return {"error": f"未知工具: {name!r}"}
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            args = args or {}
            if not isinstance(args, dict):
                return {"error": "工具参数必须是 JSON 对象"}
            return handlers[name](**args)
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
]
