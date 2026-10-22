# -*- coding: utf-8 -*-
"""通用 JSON 记录仓储：统一 ID 校验、原子写入与列表读取。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class JsonRecordRepository(Generic[T]):
    """一个目录下「ID.json」记录的仓储。

    只负责持久化；业务 Store 通过组合使用它，保持各自的特有方法。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        id_pattern: str,
        decode: Callable[[dict], T],
        encode: Callable[[T], dict],
        label: str,
        sort_key: Callable[[T], str],
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._id_pattern = re.compile(id_pattern)
        self._decode = decode
        self._encode = encode
        self._label = label
        self._sort_key = sort_key

    def path(self, record_id: str) -> Path:
        if not self._id_pattern.fullmatch(record_id):
            raise ValueError(f"{self._label} ID 格式无效: {record_id}")
        return self.root / f"{record_id}.json"

    def get(self, record_id: str) -> T:
        path = self.path(record_id)
        if not path.exists():
            raise FileNotFoundError(f"{self._label}不存在: {record_id}")
        return self._decode(json.loads(path.read_text(encoding="utf-8")))

    def put(self, record_id: str, value: T) -> T:
        path = self.path(record_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._encode(value), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return value

    def delete(self, record_id: str) -> None:
        path = self.path(record_id)
        if not path.exists():
            raise FileNotFoundError(f"{self._label}不存在: {record_id}")
        path.unlink()

    def list(self) -> list[T]:
        records: list[T] = []
        for path in self.root.glob("*.json"):
            try:
                records.append(self._decode(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(records, key=self._sort_key, reverse=True)
