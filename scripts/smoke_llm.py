# -*- coding: utf-8 -*-
"""LLM 冒烟测试：验证连通性与工具调用。

用法：
    python scripts/smoke_llm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # 非交互输出环境无需调整
    pass

from coc_keeper.agent.agent import KeeperAgent
from coc_keeper.agent.llm import LLMClient
from coc_keeper.agent.state import Session
from coc_keeper.config import Settings


def main() -> None:
    s = Settings()
    print(f"[1] 配置: {s.describe()}")
    if not s.is_configured:
        sys.exit("未配置 LLM，请在 .env 设置 DEEPSEEK_API_KEY（可选 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）")

    # 1. 连通性：纯文本
    llm = LLMClient(s)
    r = llm.chat([{"role": "user", "content": "只回复两个字：收到"}], max_tokens=16)
    print(f"[2] 连通性 OK: {r.content!r}")

    # 2. 工具调用：让 Agent 做一次侦查检定
    session = Session()
    session.investigator.skills["侦查"] = 70  # 固定技能值便于观察
    agent = KeeperAgent(session, s)
    reply = agent.respond("我要查看这间旧书房，请帮我做一次侦查检定")
    print("[3] Agent 回复:")
    print(reply)
    print("[4] 角色状态(SAN/HP 应保持):", session.investigator.to_dict()["derived"])


if __name__ == "__main__":
    main()
