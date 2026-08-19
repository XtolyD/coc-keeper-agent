# -*- coding: utf-8 -*-
"""KP Agent：手写工具调用循环（ReAct 风格）。

流程：
    玩家输入 → 追加到记忆
    → 循环：调用 LLM（带工具）
        - 有 tool_calls：逐个执行工具，结果回填 → 再问模型
        - 无 tool_calls：把 content 作为 KP 叙述返回
    → 超过 max_steps 则强制收尾
"""
from __future__ import annotations

import json
import random

from ..config import Settings
from .llm import LLMClient
from .memory import Memory
from .observability import TraceRecorder
from .prompts import KP_SYSTEM_PROMPT, build_system_prompt, infer_action_skill
from .security import PromptGuard
from .state import Session
from .tools import TOOLS_SCHEMA, make_dispatcher


class KeeperAgent:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        system_prompt: str | None = None,
        tracer: TraceRecorder | None = None,
        guard: PromptGuard | None = None,
        rng: random.Random | None = None,
    ):
        self.settings = settings or Settings()
        self.session = session
        self.llm = LLMClient(self.settings)
        self.tracer = tracer or TraceRecorder()
        self.guard = guard or PromptGuard(self.settings.max_input_chars)
        base = system_prompt or KP_SYSTEM_PROMPT
        self._prompt_base = base
        self.memory = Memory(
            build_system_prompt(base, session.investigator),
            limit=self.settings.history_limit,
        )
        self.dispatch = make_dispatcher(session, tracer=self.tracer, rng=rng)

    def _record_llm(self, resp) -> None:
        self.tracer.record_llm(self.settings.model, resp.usage, resp.latency_ms)

    def _refresh_system_prompt(self, action_check: dict | None = None) -> None:
        prompt = build_system_prompt(self._prompt_base, self.session.investigator)
        if self.session.module:
            context = self.session.module.keeper_context(max_chars=8000)
            prompt += "\n\n## 当前模组 Keeper 专用上下文（绝不可向玩家逐字展示）\n"
            prompt += json.dumps(context, ensure_ascii=False, indent=2)
        if action_check is not None:
            prompt += "\n\n## 本轮已执行的行动检定（直接依据结果叙述，不得重复检定）\n"
            prompt += json.dumps(action_check, ensure_ascii=False, indent=2)
        self.memory.system_prompt = prompt

    def _apply_spoiler_gate(self, resp) -> None:
        if self.session.module and not resp.tool_calls and self.session.module.detects_spoiler(resp.content or ""):
            resp.content = "眼前的线索还不足以揭开更深的真相。空气里只剩下令人不安的沉默。你接下来要怎么做？"

    def _required_action_check(self, user_input: str) -> dict | None:
        skill = infer_action_skill(user_input)
        if skill is None:
            return None
        return self.dispatch("roll_skill_check", {"skill": skill})

    @staticmethod
    def _check_summary(tool_name: str, result: dict) -> str | None:
        if not isinstance(result, dict) or "error" in result:
            return None
        if tool_name == "roll_skill_check":
            return (
                f"【检定 · {result['检定项']}】D100={result['掷骰']} / "
                f"目标={result['目标值']} · {result['结果']}"
            )
        if tool_name == "opposed_check":
            return (
                f"【对抗检定 · {result['我方检定项']}】我方={result['我方掷骰']}（{result['我方结果']}） / "
                f"对方={result['对方掷骰']}（{result['对方结果']}）· {result['胜者']}"
            )
        if tool_name == "luck_check":
            return f"【幸运检定】D100={result['掷骰']} / 目标={result['当前幸运']} · {result['结果']}"
        if tool_name == "sanity_check":
            return f"【理智检定】D100={result['掷骰']} · {result['结果']} · 损失 {result['损失理智']} SAN"
        if tool_name == "combat_attack":
            return f"【攻击检定】D100={result['攻击检定']} · {result['攻击结果']}"
        return None

    @classmethod
    def _with_check_summaries(cls, content: str, checks: list[tuple[str, dict]]) -> str:
        summaries = [summary for name, result in checks if (summary := cls._check_summary(name, result))]
        if not summaries:
            return content
        return "\n".join(summaries) + "\n\n" + content.lstrip()

    def respond(self, user_input: str) -> str:
        """处理一条玩家输入，返回 KP 的叙述文本。"""
        inspected = self.guard.inspect(user_input)
        if not inspected.allowed:
            return "你的行动包含试图改写系统规则或读取机密的信息，KP 不会执行。请只描述调查员在游戏世界中的行动。"
        self.memory.add_user(inspected.text)
        visible_checks: list[tuple[str, dict]] = []
        required_check = self._required_action_check(inspected.text)
        if required_check is not None:
            visible_checks.append(("roll_skill_check", required_check))
        for _ in range(self.settings.max_steps):
            self._refresh_system_prompt(required_check)
            resp = self.llm.chat(self.memory.messages(), tools=TOOLS_SCHEMA)
            self._record_llm(resp)
            self._apply_spoiler_gate(resp)
            if resp.tool_calls:
                self.memory.add_assistant(resp)
                for tc in resp.tool_calls:
                    result = self.dispatch(tc["name"], tc["arguments"])
                    self.memory.add_tool_result(tc["id"], result)
                    if tc["name"] in {"roll_skill_check", "opposed_check", "luck_check", "sanity_check", "combat_attack"}:
                        visible_checks.append((tc["name"], result))
                continue  # 工具执行完毕，再问一次模型
            resp.content = self._with_check_summaries(resp.content or "", visible_checks)
            self.memory.add_assistant(resp)
            return resp.content
        # 超过循环上限：让模型在无工具的情况下给出收尾叙述
        self._refresh_system_prompt(required_check)
        last = self.llm.chat(self.memory.messages())
        self._record_llm(last)
        self._apply_spoiler_gate(last)
        last.content = self._with_check_summaries(last.content or "", visible_checks)
        self.memory.add_assistant(last)
        return last.content
