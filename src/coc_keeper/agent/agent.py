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

from ..config import Settings
from .llm import LLMClient
from .memory import Memory
from .prompts import KP_SYSTEM_PROMPT, build_system_prompt
from .state import Session
from .tools import TOOLS_SCHEMA, make_dispatcher


class KeeperAgent:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        system_prompt: str | None = None,
    ):
        self.settings = settings or Settings()
        self.session = session
        self.llm = LLMClient(self.settings)
        base = system_prompt or KP_SYSTEM_PROMPT
        self.memory = Memory(
            build_system_prompt(base, session.investigator),
            limit=self.settings.history_limit,
        )
        self.dispatch = make_dispatcher(session)

    def respond(self, user_input: str) -> str:
        """处理一条玩家输入，返回 KP 的叙述文本。"""
        self.memory.add_user(user_input)
        for _ in range(self.settings.max_steps):
            resp = self.llm.chat(self.memory.messages(), tools=TOOLS_SCHEMA)
            self.memory.add_assistant(resp)
            if resp.tool_calls:
                for tc in resp.tool_calls:
                    result = self.dispatch(tc["name"], tc["arguments"])
                    self.memory.add_tool_result(tc["id"], result)
                continue  # 工具执行完毕，再问一次模型
            return resp.content or ""
        # 超过循环上限：让模型在无工具的情况下给出收尾叙述
        last = self.llm.chat(self.memory.messages())
        self.memory.add_assistant(last)
        return last.content or ""
