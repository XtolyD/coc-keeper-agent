# -*- coding: utf-8 -*-
"""工具注册表：把 schema 与 dispatcher 收束为一个可注入对象。"""
from __future__ import annotations

import random
from typing import Any, Callable

from .state import Session
from .tool_schemas import TOOLS_SCHEMA
from .tools import make_dispatcher


class ToolRegistry:
    """KP Agent 的工具入口（组合 dispatcher，不改变工具实现）。"""

    def __init__(
        self,
        session: Session,
        *,
        rule_index: Any = None,
        tracer: Any = None,
        rng: random.Random | None = None,
    ):
        self.schema = TOOLS_SCHEMA
        self._dispatch: Callable[[str, Any], dict] = make_dispatcher(
            session, rule_index=rule_index, tracer=tracer, rng=rng,
        )

    def dispatch(self, name: str, arguments: Any) -> dict:
        return self._dispatch(name, arguments)
