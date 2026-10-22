# -*- coding: utf-8 -*-
"""Agent 可观测性：记录 LLM 与工具调用、延迟和 token 用量。"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    name: str
    started_at: float
    latency_ms: float
    input: Any = None
    output: Any = None
    usage: dict[str, int] = field(default_factory=dict)


class TraceRecorder:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record_tool(self, name: str, arguments: dict, result: dict, *, latency_ms: float = 0.0) -> None:
        self.events.append(TraceEvent("tool", name, time.time(), latency_ms, arguments, result))

    def record_llm(self, model: str, usage: dict[str, int], latency_ms: float) -> None:
        self.events.append(TraceEvent("llm", model, time.time(), latency_ms, usage=usage))

    def summary(self) -> dict[str, int | float]:
        llm = [event for event in self.events if event.kind == "llm"]
        tools = [event for event in self.events if event.kind == "tool"]
        return {
            "llm_calls": len(llm),
            "tool_calls": len(tools),
            "prompt_tokens": sum(e.usage.get("prompt_tokens", 0) for e in llm),
            "completion_tokens": sum(e.usage.get("completion_tokens", 0) for e in llm),
            "total_tokens": sum(e.usage.get("total_tokens", 0) for e in llm),
            "latency_ms": round(sum(e.latency_ms for e in self.events), 3),
        }

    def estimate_cost(self, input_per_million: float, output_per_million: float) -> float:
        """按调用方提供的供应商单价估算美元成本，避免硬编码易过期价格。"""
        summary = self.summary()
        return round(
            summary["prompt_tokens"] * float(input_per_million) / 1_000_000
            + summary["completion_tokens"] * float(output_per_million) / 1_000_000,
            8,
        )

    def export_jsonl(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "\n".join(json.dumps(asdict(event), ensure_ascii=False) for event in self.events) + "\n",
            encoding="utf-8",
        )
        return destination
