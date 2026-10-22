# -*- coding: utf-8 -*-
"""DeepSeek 视觉客户端（独立层）：分析图片（地图/角色卡/插图/表格）。

提供三类识别，供 `module/`（模组语义）与 `retrieval/`（规则书图块）复用：
- `VisionResult`：一次识别的结果（content_type + data + description）。
- `VisionClient`：基于 OpenAI SDK 的 DeepSeek 视觉客户端。

封装「按需 thinking + 充足 max_tokens + JSON 输出」——实测得出的稳定配置，
集中在 VisionClient 一处。可注入真实 client 或 mock（供单测）。

关键实测结论（见 docs/module-spec.md §2）：
- max_tokens 是上限非强制：设 393216（API 上限）时模型「够用即停」，不浪费。
- 不传 thinking（默认）：模型按需决定是否思考；配合大 max_tokens 不会截断。
- response_format=json_object：保证结构化输出合法。
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import Settings

# API 允许的 max_tokens 上限（实测：设 1M 报 400，上限 393216）
MAX_TOKENS = 393216

# 视觉识别的页面类型
CONTENT_TYPES = ("text", "map", "character", "illustration", "table")


@dataclass
class VisionResult:
    """一次图片识别的结果。"""
    content_type: str          # 图片类型，见 CONTENT_TYPES
    data: dict                 # 结构化数据（如 map 的地名列表、character 的属性）
    description: str = ""      # 自然语言描述

    def to_dict(self) -> dict:
        return {"content_type": self.content_type, "data": self.data,
                "description": self.description}


class VisionClient:
    """基于 OpenAI SDK 的 DeepSeek 视觉客户端。"""

    def __init__(self, client: Optional[object] = None):
        """client 可注入真实 OpenAI 客户端或 mock（测试用）。

        默认从 Settings 构建，读取 .env 配置。
        """
        self.client = client
        self._own_client = client is None

    def _get_client(self) -> object:
        if self._own_client and self.client is None:
            s = Settings()
            from openai import OpenAI
            self.client = OpenAI(api_key=s.api_key, base_url=s.base_url)
        return self.client

    def _read_b64(self, image_path: str, image_mime: str) -> str:
        return base64.b64encode(Path(image_path).read_bytes()).decode()

    def recognize_page(self, image_path: str, image_mime: str = "image/png") -> VisionResult:
        """识别单个图片 → 类型 + 结构化数据。"""
        content = [
            {"type": "text", "text": CLASSIFY_PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{image_mime};base64,{self._read_b64(image_path, image_mime)}"}},
        ]
        return self._parse(self._chat(content))

    def recognize_map(self, image_path: str, image_mime: str = "image/png") -> dict:
        """识别地图 → 地名列表 JSON。"""
        content = [
            {"type": "text", "text": MAP_PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{image_mime};base64,{self._read_b64(image_path, image_mime)}"}},
        ]
        return self._parse_json(self._chat(content))

    def recognize_character(self, image_path: str, image_mime: str = "image/png") -> dict:
        """识别角色卡 → 属性/技能 JSON。"""
        content = [
            {"type": "text", "text": CHARACTER_PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{image_mime};base64,{self._read_b64(image_path, image_mime)}"}},
        ]
        return self._parse_json(self._chat(content))

    def review_chunks(self, prompt: str, image_paths: list[str]) -> dict:
        """DeepSeek 复核：正文 + 可选图片，返回结构化 JSON。"""
        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            mime = "image/jpeg" if str(path).lower().endswith((".jpg", ".jpeg")) else "image/png"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{self._read_b64(path, mime)}"},
            })
        return self._parse_json(self._chat(content))

    # ---- 内部实现 ---------------------------------------------------------
    def _chat(self, content: list[dict]) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=Settings().model,
            messages=[{"role": "user", "content": content}],
            max_tokens=MAX_TOKENS,
            # 不传 thinking → 模型按需思考（定案，见 docs/module-spec.md §2）
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""

    @staticmethod
    def _parse(raw: str) -> VisionResult:
        data = VisionClient._parse_json(raw)
        content_type = data.get("content_type", "text")
        if content_type not in CONTENT_TYPES:
            content_type = "text"
        return VisionResult(
            content_type=content_type,
            data=data,
            description=data.get("description", ""),
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """解析模型返回的 JSON 字符串（容错：剥掉 ```json 围栏 / 前后噪声）。"""
        raw = raw.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"content_type": "text", "description": raw}


# ---- 提示词 ------------------------------------------------------------------
# 分类提示：判断图片属于哪种类型，并给出通用描述。
CLASSIFY_PROMPT = (
    "你是CoC跑团模组解析器。判断这张图片属于哪种类型，并抽取其内容。"
    '只输出JSON：{"content_type":"text|map|character|illustration|table",'
    '"description":"该图内容简述（中文）"}。'
    "若这是地图，content_type取map并尽量在description中列出地名；"
    "若是调查员角色卡，content_type取character；"
    "若是插图，content_type取illustration；"
    "若含表格，content_type取table。"
)

# 地图提示：抽地名列表。
MAP_PROMPT = (
    '这是CoC模组的一张地图。只输出JSON：{"content_type":"map","locations":["地名1","地名2"],'
    '"description":"地图简述"}。尽可能完整列出图中所有可见地名/地点标签（中文，用逗号分隔为数组）。'
)

# 角色卡提示：抽取属性/技能 JSON。
CHARACTER_PROMPT = (
    '这是CoC 7th一张调查员角色卡。抽取为JSON：'
    '{"content_type":"character","name":"姓名","age":"年龄","occupation":"职业",'
    '"attributes":{"STR":数字,"CON":数字,"DEX":数字,...},'
    '"hp":"当前/最大","mp":"当前/最大","san":"当前/最大","san_max":数字,'
    '"skills":{"技能名":百分比,...,},"weapons":[{"name":"武器名","damage":"伤害"}]}。'
    "只输出JSON，字段缺失就省略该字段。"
)
