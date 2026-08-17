# -*- coding: utf-8 -*-
"""LLM 客户端封装（OpenAI 兼容接口，适用于 micuapi / OpenRouter / DeepSeek 等）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from openai import OpenAI

from ..config import Settings


@dataclass
class LLMResponse:
    """一次 LLM 调用的结果。"""
    content: Optional[str] = None
    tool_calls: list[dict] = field(default_factory=list)


class LLMClient:
    """基于 OpenAI SDK 的兼容客户端。换供应商只需改 .env。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.is_configured:
            raise RuntimeError(
                "LLM 未配置：请在 .env 中设置 DEEPSEEK_API_KEY（可选 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）"
            )
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.temperature,
            "max_tokens": max_tokens or self.settings.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return LLMResponse(
            content=msg.content,
            tool_calls=[
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in (msg.tool_calls or [])
            ],
        )
