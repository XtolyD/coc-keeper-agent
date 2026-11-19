# -*- coding: utf-8 -*-
"""工具 schema：与 handlers 分离，便于注册表与一致性测试。"""
from __future__ import annotations


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
            "name": "set_skill",
            "description": "设置当前调查员的技能值，用于建卡或技能成长。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "技能名称"},
                    "value": {"type": "integer", "description": "新的技能值，0到100"},
                },
                "required": ["skill", "value"],
            },
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
                    "type": {"type": "string", "enum": ["rule", "skill", "combat", "monster", "spell", "tome", "table", "glossary"],
                             "description": "（可选）限定实体类型，不传则全库检索"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认3"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_skill",
            "description": "根据玩家行动返回可能适用的技能候选、角色当前值和技能用法。只是参考，最终由 KP 选择。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "玩家行动原文"},
                    "limit": {"type": "integer", "description": "最多候选数，默认3"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "按关键词或类别检索技能说明、别名、使用场景和替代技能。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "技能名、别名或用途关键词"},
                    "category": {"type": "string", "description": "可选类别：investigation/social/combat/physical/technical/knowledge/medical/art/other"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "获取单个技能的完整说明、基础值、难度、孤注一掷与失败风格。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名或别名，如 会计、取悦、表演、手枪"},
                    "section": {"type": "string", "description": "可选：只看某个说明段落"},
                },
                "required": ["name"],
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
