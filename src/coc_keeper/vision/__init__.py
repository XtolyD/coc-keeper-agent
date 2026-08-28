# -*- coding: utf-8 -*-
"""DeepSeek 视觉（独立层）：分析图片（地图/角色卡/插图/表格）。

供 `module/`（模组语义）与 `retrieval/`（规则书图块）复用。核心：
- `VisionClient.recognize_page/map/character` → VisionResult / dict
- `VisionResult`：识别结果数据类
"""
from __future__ import annotations

from .client import CONTENT_TYPES, MAX_TOKENS, VisionClient, VisionResult

__all__ = ["VisionClient", "VisionResult", "CONTENT_TYPES", "MAX_TOKENS"]
