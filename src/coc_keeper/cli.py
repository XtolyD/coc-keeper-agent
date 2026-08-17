# -*- coding: utf-8 -*-
"""交互式 CLI：单人跑团入口。

用法：
    python -m coc_keeper.cli
退出：输入 exit / quit / 退出。
"""
from __future__ import annotations

import sys

# Windows 控制台强制 UTF-8，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 —— 非交互环境忽略
    pass

from .agent.agent import KeeperAgent
from .agent.state import Session
from .character import create_character
from .config import Settings


def _print_sheet(sheet) -> None:
    d = sheet.to_dict()
    print("\n===== 调查员角色卡 =====")
    print(f"姓名：{d['name']}（{d['age']}岁）")
    print("属性：", " ".join(f"{k}{v}" for k, v in d["attributes"].items()))
    print("衍生：", " ".join(f"{k}:{v}" for k, v in d["derived"].items()))
    print("技能(非零)：", ", ".join(f"{k}{v}%" for k, v in d["skills"].items() if v))
    print("========================\n")


def main() -> None:
    settings = Settings()
    print(f"[KP Agent] {settings.describe()}")
    if not settings.is_configured:
        print("错误：未配置 LLM。请在 .env 中设置 DEEPSEEK_API_KEY（可选 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）")
        sys.exit(1)

    session = Session()
    _print_sheet(session.investigator)

    agent = KeeperAgent(session, settings)
    print("输入「exit」退出。祝你……活下来。\n")

    while True:
        try:
            user = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit", "退出"):
            print("再见。")
            break
        reply = agent.respond(user)
        print(f"\nKP> {reply}\n")


if __name__ == "__main__":
    main()
