# -*- coding: utf-8 -*-
"""pytest 根配置：把 src 加入导入路径，并提供脚本化伪随机数生成器。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


@pytest.fixture
def scripted():
    """返回一个按给定序列出值的伪 RNG，用于确定性测试。

    用法：rng = scripted(5, 2);  # 第 1 次 randint -> 5，第 2 次 -> 2
    """
    class ScriptedRng:
        def __init__(self, *vals):
            self.vals = list(vals)
            self.i = 0

        def randint(self, a, b):
            assert self.i < len(self.vals), "scripted rng 序列已用尽"
            v = self.vals[self.i]
            self.i += 1
            return v

    return ScriptedRng
