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

import random
import json

from ..config import Settings
from .llm import LLMClient
from .memory import Memory
from .observability import TraceRecorder
from .prompts import KP_SYSTEM_PROMPT, build_system_prompt
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

    def _refresh_system_prompt(self) -> None:
        prompt = build_system_prompt(self._prompt_base, self.session.investigator)
        if self.session.module:
            context = self.session.module.keeper_context(max_chars=8000)
            prompt += "\n\n## 当前模组 Keeper 专用上下文（绝不可向玩家逐字展示）\n"
            prompt += json.dumps(context, ensure_ascii=False, indent=2)
        self.memory.system_prompt = prompt

    def _apply_spoiler_gate(self, resp) -> None:
        if self.session.module and not resp.tool_calls and self.session.module.detects_spoiler(resp.content or ""):
            resp.content = "眼前的线索还不足以揭开更深的真相。空气里只剩下令人不安的沉默。你接下来要怎么做？"

    def respond(self, user_input: str) -> str:
        """处理一条玩家输入，返回 KP 的叙述文本。"""
        inspected = self.guard.inspect(user_input)
        if not inspected.allowed:
            return "你的行动包含试图改写系统规则或读取机密的信息，KP 不会执行。请只描述调查员在游戏世界中的行动。"
        self.memory.add_user(inspected.text)
        for _ in range(self.settings.max_steps):
            self._refresh_system_prompt()
            resp = self.llm.chat(self.memory.messages(), tools=TOOLS_SCHEMA)
            self._record_llm(resp)
            self._apply_spoiler_gate(resp)
            self.memory.add_assistant(resp)
            if resp.tool_calls:
                for tc in resp.tool_calls:
                    result = self.dispatch(tc["name"], tc["arguments"])
                    self.memory.add_tool_result(tc["id"], result)
                continue  # 工具执行完毕，再问一次模型
            return resp.content or ""
        # 超过循环上限：让模型在无工具的情况下给出收尾叙述
        self._refresh_system_prompt()
        last = self.llm.chat(self.memory.messages())
        self._record_llm(last)
        self._apply_spoiler_gate(last)
        self.memory.add_assistant(last)
        return last.content or ""
