# -*- coding: utf-8 -*-
"""对话记忆：管理 system 提示与历史消息，按「回合」安全裁剪。"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .llm import LLMResponse


class Memory:
    """保存对话历史。裁剪以完整回合为单位，避免拆散 tool_calls 序列。"""

    def __init__(self, system_prompt: str, limit: int = 40):
        self.system_prompt = system_prompt
        self.limit = limit
        self._messages: list[dict[str, Any]] = []

    def messages(self) -> list[dict[str, Any]]:
        return [{"role": "system", "content": self.system_prompt}] + self._messages

    def snapshot(self) -> list[dict[str, Any]]:
        return deepcopy(self._messages)

    def restore(self, messages: list[dict[str, Any]]) -> None:
        self._messages = deepcopy(messages)
        self._trim()

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, resp: LLMResponse) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        if resp.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in resp.tool_calls
            ]
        self._messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id: str, result: Any) -> None:
        self._messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(result, ensure_ascii=False)}
        )
        self._trim()

    def _trim(self) -> None:
        """从最旧的完整回合开始丢弃，直到消息数 <= limit。"""
        while len(self._messages) > self.limit:
            first_user = next(
                (i for i, m in enumerate(self._messages) if m["role"] == "user"), None
            )
            if first_user is None:
                break
            next_user = next(
                (i for i in range(first_user + 1, len(self._messages)) if self._messages[i]["role"] == "user"),
                len(self._messages),
            )
            # 当前未完结回合（最后一条 user 之后无下一条 user）不裁剪
            if next_user == len(self._messages):
                break
            del self._messages[first_user:next_user]
