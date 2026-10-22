# -*- coding: utf-8 -*-
"""交互式 CLI：单人跑团入口。

用法：
    python -m coc_keeper.cli
退出：输入 exit / quit / 退出。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

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
from .evaluation import default_rule_suite
from .module_service import ModuleApplicationService
from .module_store import ModuleStore
from .modules import KeeperModule, ModuleRuntime
from .web_jobs import JobManager


def _load_module(path: str | Path, title: str | None = None) -> ModuleRuntime:
    source = Path(path)
    if source.suffix.lower() == ".pdf":
        service = ModuleApplicationService(ModuleStore(Path("data") / "modules"), JobManager())
        module = service.load_pdf(source, title=title, progress=lambda stage: print(f"[模组] {stage}"))
        return ModuleRuntime(module)
    return ModuleRuntime(KeeperModule.load(source))


def _print_sheet(sheet) -> None:
    d = sheet.to_dict()
    print("\n===== 调查员角色卡 =====")
    print(f"姓名：{d['name']}（{d['age']}岁）")
    print("属性：", " ".join(f"{k}{v}" for k, v in d["attributes"].items()))
    print("衍生：", " ".join(f"{k}:{v}" for k, v in d["derived"].items()))
    print("技能(非零)：", ", ".join(f"{k}{v}%" for k, v in d["skills"].items() if v))
    print("========================\n")


def _run_eval() -> int:
    suite = default_rule_suite()
    results = suite.run()
    print(json.dumps({"summary": suite.score(results), "results": [r.__dict__ for r in results]}, ensure_ascii=False, indent=2))
    return 0 if all(result.passed for result in results) else 1


def _handle_command(command: str, session: Session, agent: KeeperAgent, autosave: Path | None) -> bool:
    """处理斜杠命令；返回 True 表示命令已处理。"""
    name, _, argument = command.partition(" ")
    if name == "/help":
        print("/status 角色卡 | /players 玩家 | /trace 追踪 | /save [路径] 保存")
        print("/module add <PDF或JSON> | /module status | /module next <原因> | /module export <JSON>")
    elif name == "/status":
        _print_sheet(session.investigator)
    elif name == "/players":
        print("玩家：" + "、".join(session.players))
    elif name == "/trace":
        print(json.dumps(agent.tracer.summary(), ensure_ascii=False, indent=2))
    elif name == "/save":
        target = Path(argument.strip()) if argument.strip() else autosave
        if target is None:
            target = Path("saves") / "campaign.json"
        print(f"已保存：{session.save(target).resolve()}")
    elif name == "/module":
        action, _, value = argument.strip().partition(" ")
        value = value.strip().strip('"').strip("'")
        if action == "add" and value:
            session.module = _load_module(value)
            manifest = Path("data") / "modules" / f"{Path(value).stem}.json"
            session.module.module.save(manifest)
            print(f"已加载模组《{session.module.module.title}》。")
            print(f"可编辑场景清单：{manifest.resolve()}")
        elif action == "status":
            print(json.dumps(session.module.status(player_safe=True) if session.module else {"loaded": False}, ensure_ascii=False, indent=2))
        elif action == "next" and value:
            if session.module is None:
                print("当前未加载模组。")
            else:
                result = session.module.advance(value, session.module.current.objectives)
                print(json.dumps(result, ensure_ascii=False, indent=2))
        elif action == "export" and value:
            if session.module is None:
                print("当前未加载模组。")
            else:
                print(f"已导出：{session.module.module.save(value).resolve()}")
        else:
            print("用法：/module add <PDF或JSON> | status | next <原因> | export <JSON>")
    else:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="CoC 7th KP Agent")
    parser.add_argument("--load", type=Path, help="加载战役 JSON 存档")
    parser.add_argument("--autosave", type=Path, help="退出时自动保存到指定路径")
    parser.add_argument("--seed", type=int, help="固定随机种子，便于复现")
    parser.add_argument("--module", type=Path, help="启动时加载 PDF 或 JSON 模组")
    parser.add_argument("--eval", action="store_true", help="运行离线评估后退出（无需 LLM）")
    args = parser.parse_args()
    if args.eval:
        raise SystemExit(_run_eval())

    settings = Settings()
    print(f"[KP Agent] {settings.describe()}")
    if not settings.is_configured:
        print("错误：未配置 LLM。请在 .env 中设置 DEEPSEEK_API_KEY（可选 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）")
        sys.exit(1)

    rng = random.Random(args.seed) if args.seed is not None else None
    session = Session.load(args.load) if args.load else Session(
        investigator=create_character(rng=rng)
    )
    if args.module:
        session.module = _load_module(args.module)
    _print_sheet(session.investigator)

    agent = KeeperAgent(session, settings, rng=rng)
    print("输入「exit」退出，输入 /help 查看命令。祝你……活下来。\n")

    while True:
        try:
            user = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            if args.autosave:
                print(f"\n已自动保存：{session.save(args.autosave).resolve()}")
            print("\n再见。")
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit", "退出"):
            if args.autosave:
                print(f"已自动保存：{session.save(args.autosave).resolve()}")
            print("再见。")
            break
        if user.startswith("/") and _handle_command(user, session, agent, args.autosave):
            continue
        reply = agent.respond(user)
        print(f"\nKP> {reply}\n")


if __name__ == "__main__":
    main()
