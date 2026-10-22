# -*- coding: utf-8 -*-
"""固定随机种子的离线评估套件。"""
from __future__ import annotations

import random
import json
from dataclasses import dataclass
from typing import Callable, Iterable

from .dice import Difficulty, d100
from .rules.checks import indefinite_insanity_triggered, skill_check
from .rules.combat import Combatant, Weapon, resolve_attack
from .retrieval import Index, search


@dataclass(frozen=True)
class EvalCase:
    name: str
    run: Callable[[], bool]
    category: str = "rules"


@dataclass(frozen=True)
class EvalResult:
    name: str
    category: str
    passed: bool
    error: str = ""


class EvaluationSuite:
    def __init__(self, cases: Iterable[EvalCase]):
        self.cases = list(cases)

    def run(self) -> list[EvalResult]:
        results: list[EvalResult] = []
        for case in self.cases:
            try:
                results.append(EvalResult(case.name, case.category, bool(case.run())))
            except Exception as exc:  # noqa: BLE001 - 评估必须记录单例失败并继续
                results.append(EvalResult(case.name, case.category, False, f"{type(exc).__name__}: {exc}"))
        return results

    @staticmethod
    def score(results: Iterable[EvalResult]) -> dict[str, float | int]:
        items = list(results)
        passed = sum(result.passed for result in items)
        return {"passed": passed, "total": len(items), "score": passed / max(1, len(items))}


@dataclass(frozen=True)
class NarrativeRubric:
    responds_to_action: float
    preserves_player_agency: float
    sensory_detail: float
    rule_discipline: float

    @property
    def score(self) -> float:
        return round((self.responds_to_action + self.preserves_player_agency + self.sensory_detail + self.rule_discipline) / 4, 3)


def evaluate_narrative(text: str, *, used_tools: bool = True) -> NarrativeRubric:
    """无需 LLM judge 的可复现叙事基线；线上评估可替换为同结构 judge。"""
    content = str(text).strip()
    sensory_terms = ("声音", "气味", "温度", "阴影", "潮湿", "冰冷", "昏暗", "脚步")
    agency_terms = ("你要", "你可以", "怎么办", "选择", "接下来")
    return NarrativeRubric(
        responds_to_action=1.0 if len(content) >= 10 else 0.0,
        preserves_player_agency=1.0 if any(term in content for term in agency_terms) else 0.5,
        sensory_detail=1.0 if any(term in content for term in sensory_terms) else 0.0,
        rule_discipline=1.0 if used_tools else 0.0,
    )


def evaluate_narrative_with_llm(text: str, llm) -> NarrativeRubric:
    """使用兼容 ``LLMClient`` 的 judge 生成结构化叙事评分。"""
    schema = [{
        "type": "function",
        "function": {
            "name": "submit_rubric",
            "description": "提交四项 0 到 1 的叙事评分",
            "parameters": {
                "type": "object",
                "properties": {
                    "responds_to_action": {"type": "number", "minimum": 0, "maximum": 1},
                    "preserves_player_agency": {"type": "number", "minimum": 0, "maximum": 1},
                    "sensory_detail": {"type": "number", "minimum": 0, "maximum": 1},
                    "rule_discipline": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["responds_to_action", "preserves_player_agency", "sensory_detail", "rule_discipline"],
            },
        },
    }]
    response = llm.chat([
        {"role": "system", "content": "你是 CoC KP 叙事评估员。只根据给定文本评分，不补充剧情。"},
        {"role": "user", "content": text},
    ], tools=schema, tool_choice="required", temperature=0, max_tokens=256)
    if not response.tool_calls or response.tool_calls[0]["name"] != "submit_rubric":
        raise ValueError("LLM judge 未返回 submit_rubric 工具调用")
    values = json.loads(response.tool_calls[0]["arguments"])

    def score(name: str) -> float:
        return max(0.0, min(1.0, float(values[name])))

    return NarrativeRubric(
        score("responds_to_action"), score("preserves_player_agency"),
        score("sensory_detail"), score("rule_discipline"),
    )


def default_rule_suite(seed: int = 1920) -> EvaluationSuite:
    """覆盖骰子、难度、疯狂、战斗、检索的最小硬指标。"""

    def d100_range() -> bool:
        rng = random.Random(seed)
        return all(1 <= d100(rng=rng) <= 100 for _ in range(1000))

    def hard_check_consistent() -> bool:
        result = skill_check(60, Difficulty.HARD, rng=random.Random(seed))
        return result.target == 30 and result.success == (result.roll <= 30 or result.roll == 1)

    def insanity_threshold() -> bool:
        return indefinite_insanity_triggered(10, 50) and not indefinite_insanity_triggered(9, 50)

    def combat_stays_bounded() -> bool:
        attacker = Combatant("调查员", 10, 10, db="0")
        target = Combatant("食尸鬼", 12, 12, armor=1)
        result = resolve_attack(attacker, target, 100, Weapon("匕首", "1d4"), rng=random.Random(seed))
        return 0 <= target.hp <= 12 and (not result.hit or result.damage is not None)

    def retrieval_has_citation() -> bool:
        index = Index.build([{
            "name": "", "text": "奖励骰需要额外掷一个十位骰，取较小结果。",
            "page": 70, "start_page": 70, "end_page": 70, "path": "", "lines": [],
        }])
        hits = search(index, "奖励骰")
        return bool(hits and hits[0].page == 70)

    return EvaluationSuite([
        EvalCase("d100_range", d100_range),
        EvalCase("hard_check", hard_check_consistent),
        EvalCase("insanity_threshold", insanity_threshold),
        EvalCase("combat_bounds", combat_stays_bounded),
        EvalCase("retrieval_citation", retrieval_has_citation, "rag"),
    ])
