# -*- coding: utf-8 -*-
"""会话状态：一局跑团中需要被工具读写、被持久化的可变状态。"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..character import CharacterSheet, create_character


@dataclass
class Session:
    """一局跑团的会话状态。MVP 为单调查员；M4 扩展为多人队伍。"""
    investigator: CharacterSheet = field(default_factory=create_character)
    # 场景/战役日志等长期状态在 M4 补充
