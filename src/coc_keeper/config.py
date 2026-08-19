# -*- coding: utf-8 -*-
"""配置：从 .env 加载模型与运行参数。

读取顺序：环境变量 > 工作区根目录 .env > 项目根目录 .env。
密钥只从这里读取，永不硬编码、永不打印。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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


def _openai_base_url(value: str) -> str:
    """Accept a provider origin, an OpenAI base URL, or a full completions URL."""
    raw = str(value).strip().rstrip("/")
    parts = urlsplit(raw)
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path.removesuffix("/chat/completions")
    if not path:
        path = "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


@dataclass
class Settings:
    """Agent 运行配置。默认值从环境变量读取，便于覆盖。

    预期在 .env 中声明以下变量（换任何 OpenAI 兼容供应商都只需改这三个）：
        DEEPSEEK_API_KEY   （密钥，必填）
        DEEPSEEK_BASE_URL  （默认 https://api.deepseek.com）
        DEEPSEEK_MODEL     （默认 deepseek-v4-flash）
        DEEPSEEK_CONTEXT_WINDOW （默认 1000000）
    """
    model: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    base_url: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    api_key: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", ""))
    context_window: int = field(default_factory=lambda: int(os.environ.get("DEEPSEEK_CONTEXT_WINDOW", "1000000")))

    # 运行参数
    max_steps: int = 8          # 单次 respond 的工具调用循环上限
    max_tokens: int = 2048
    temperature: float = 0.7
    history_limit: int = 80     # 近期消息；完整历史由战役存储与检索保留
    max_input_chars: int = 4000
    request_timeout: float = 60.0
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)

    @property
    def requires_reasoning_content(self) -> bool:
        """DeepSeek 思考模式的工具回合必须原样回传 reasoning_content。"""
        return "deepseek" in f"{self.model} {self.base_url}".lower()

    def describe(self) -> str:
        """返回不包含密钥的模型摘要，用于日志展示。"""
        return f"model={self.model} context_window={self.context_window} base_url={self.base_url}"


@dataclass
class GrokVisionSettings:
    """Grok-compatible vision endpoint used only for PDF page correction."""

    model: str = field(default_factory=lambda: os.environ.get("GROK_MODEL", "grok-4.5"))
    base_url: str = field(default_factory=lambda: _openai_base_url(
        os.environ.get("GROK_API", "https://api.x.ai/v1")
    ))
    api_key: str = field(default_factory=lambda: os.environ.get("GROK_API_KEY", ""))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("GROK_VISION_MAX_TOKENS", "8000")))
    temperature: float = 0.0
    request_timeout: float = field(default_factory=lambda: float(os.environ.get("GROK_VISION_TIMEOUT", "300")))
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)

    @property
    def requires_reasoning_content(self) -> bool:
        return False

    def describe(self) -> str:
        return f"model={self.model} base_url={self.base_url}"
