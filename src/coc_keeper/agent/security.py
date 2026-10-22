# -*- coding: utf-8 -*-
"""玩家输入边界与 prompt injection 防护。"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityResult:
    allowed: bool
    text: str
    flags: tuple[str, ...] = ()


class PromptGuard:
    """识别试图改写系统/工具纪律的高风险输入。

    这是确定性第一道防线；系统提示仍需明确把玩家文本视为不可信数据。
    """
    _PATTERNS = (
        ("ignore_instructions", re.compile(r"忽略.{0,12}(指令|规则|系统)|ignore.{0,12}(instruction|system)", re.I)),
        ("system_prompt", re.compile(r"系统提示词|system\s*prompt|developer\s*message", re.I)),
        ("fake_tool", re.compile(r"伪造.{0,8}(骰子|工具|结果)|不要调用.{0,8}工具|skip.{0,8}tool", re.I)),
        ("secret_exfiltration", re.compile(r"(显示|泄露|输出).{0,12}(密钥|api.?key|环境变量|隐藏指令)", re.I)),
        ("spoiler_request", re.compile(r"(告诉|显示|列出|透露).{0,12}(结局|完整剧情|幕后真相|后续场景|所有秘密)|直接剧透", re.I)),
    )

    def __init__(self, max_chars: int = 4000):
        self.max_chars = max(1, int(max_chars))

    def inspect(self, text: str) -> SecurityResult:
        cleaned = str(text).replace("\x00", "").strip()
        flags = [name for name, pattern in self._PATTERNS if pattern.search(cleaned)]
        if len(cleaned) > self.max_chars:
            flags.append("input_too_long")
        return SecurityResult(not flags, cleaned[: self.max_chars], tuple(flags))
