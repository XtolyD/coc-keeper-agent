# -*- coding: utf-8 -*-
"""配置：从 .env 加载模型与运行参数。

读取顺序：环境变量 > 工作区根目录 .env > 项目根目录 .env。
密钥只从这里读取，永不硬编码、永不打印。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录（coc-keeper-agent）= 本文件上三级
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 工作区根目录（dsh_workspace）= 项目根目录上一级
WORKSPACE_ROOT = PROJECT_ROOT.parent


def _load_dotenv() -> None:
    """手动解析 .env（KEY=VALUE 简单格式），不依赖 python-dotenv。"""
    for path in (WORKSPACE_ROOT / ".env", PROJECT_ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


@dataclass
class Settings:
    """Agent 运行配置。默认值从环境变量读取，便于覆盖。

    预期在 .env 中声明以下变量（换任何 OpenAI 兼容供应商都只需改这三个）：
        DEEPSEEK_API_KEY   （密钥，必填）
        DEEPSEEK_BASE_URL  （默认 https://api.deepseek.com）
        DEEPSEEK_MODEL     （默认 deepseek-chat）
    """
    model: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    base_url: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    api_key: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", ""))

    # 运行参数
    max_steps: int = 8          # 单次 respond 的工具调用循环上限
    max_tokens: int = 2048
    temperature: float = 0.7
    history_limit: int = 40     # 保留最近消息条数

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)

    def describe(self) -> str:
        """返回不包含密钥的模型摘要，用于日志展示。"""
        return f"model={self.model} base_url={self.base_url}"
