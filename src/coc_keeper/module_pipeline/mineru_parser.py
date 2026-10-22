# -*- coding: utf-8 -*-
"""MinerU 解析适配器：按 PDF 内容 hash 缓存 ParseResult。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from ..docparser import MinerUClient
from ..docparser.result import ParseResult, parse_content_list


class CachedMinerUDocumentParser:
    """把 MinerUClient 包装成带缓存的 DocumentParser。

    同一个 PDF 重复分析时直接读缓存，避免重复上传/解析与费用。
    """

    def __init__(self, client: MinerUClient, cache_root: str | Path):
        self.client = client
        self.cache_root = Path(cache_root)

    def parse(self, pdf_path: Path, *, refresh: bool = False) -> ParseResult:
        pdf_path = Path(pdf_path)
        key = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        cache_dir = self.cache_root / key
        if not refresh:
            cached = self._load_cache(cache_dir, pdf_path)
            if cached is not None:
                return cached
        cache_dir.mkdir(parents=True, exist_ok=True)
        result = self.client.parse_pdf(str(pdf_path), out_dir=str(cache_dir))
        self._write_meta(cache_dir, result, key)
        return result

    @staticmethod
    def _load_cache(cache_dir: Path, pdf_path: Path) -> ParseResult | None:
        if not cache_dir.exists():
            return None
        candidates = [
            p for p in cache_dir.glob("*content_list.json")
            if "v2" not in p.name
        ]
        if not candidates:
            return None
        content_path = candidates[0]
        try:
            blocks = parse_content_list(json.loads(content_path.read_text(encoding="utf-8")))
        except (ValueError, TypeError, OSError):
            return None
        full_md = cache_dir / "full.md"
        meta_path = cache_dir / "meta.json"
        parsed_at = ""
        if meta_path.exists():
            try:
                parsed_at = str(json.loads(meta_path.read_text(encoding="utf-8")).get("parsed_at", ""))
            except (ValueError, OSError):
                parsed_at = ""
        return ParseResult(
            source_pdf=str(pdf_path),
            blocks=blocks,
            markdown=full_md.read_text(encoding="utf-8") if full_md.exists() else "",
            images_dir=str(cache_dir / "images"),
            content_list_path=str(content_path),
            parsed_at=parsed_at or datetime.now().isoformat(timespec="seconds"),
        )

    @staticmethod
    def _write_meta(cache_dir: Path, result: ParseResult, key: str) -> None:
        meta = {
            "sha256": key, "source_pdf": result.source_pdf,
            "parsed_at": result.parsed_at, "blocks": len(result.blocks),
        }
        (cache_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
        )
