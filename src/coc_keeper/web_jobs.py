# -*- coding: utf-8 -*-
"""后台任务管理：替代 Web 路由中的全局任务字典与裸线程。"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobState:
    id: str
    kind: str
    status: str = "running"
    stage: str = "排队"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id, "kind": self.kind, "status": self.status,
            "stage": self.stage, "result": self.result, "error": self.error,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class JobManager:
    """线程池任务管理器。任务函数接收 report(stage) 并返回可序列化 dict。"""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="coc-job")
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: Callable[[Callable[[str], None]], dict[str, Any]]) -> str:
        job_id = uuid.uuid4().hex
        job = JobState(job_id, kind)
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run, job, fn)
        return job_id

    def _run(self, job: JobState, fn: Callable[[Callable[[str], None]], dict[str, Any]]) -> None:
        def report(stage: str) -> None:
            with self._lock:
                job.stage = stage
                job.updated_at = _now()

        try:
            result = fn(report)
        except Exception as exc:  # noqa: BLE001 - 失败必须留在任务状态里
            with self._lock:
                job.status = "failed"
                job.stage = "失败"
                job.error = f"{type(exc).__name__}: {exc}"
                job.updated_at = _now()
            return
        with self._lock:
            job.status = "completed"
            job.stage = "完成"
            job.result = result
            job.updated_at = _now()

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise FileNotFoundError(f"任务不存在: {job_id}")
        return job.to_dict()

    def latest_for(self, kind: str, module_id: str) -> dict[str, Any] | None:
        with self._lock:
            candidates = [
                job for job in self._jobs.values()
                if job.kind == kind
                and (job.result or {}).get("module_id") == module_id
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda job: job.updated_at).to_dict()
