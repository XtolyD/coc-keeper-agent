# -*- coding: utf-8 -*-
"""DeepSeek 复核：校对 MinerU 正文，并识别图片块。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..docparser.result import ParseResult
from ..modules import ModuleSourceChunk
from ..vision.client import VisionClient
from .ports import ReviewOutcome

REVIEW_PROMPT = """你是《克苏鲁的呼唤》第七版模组的校对编辑。
输入是 MinerU 解析出的结构化原文（按片段、页码、标题给出），以及可能附带的页面图片。
请忠实校对，不补写剧情，不总结，不猜测：
1. 修正双栏/文本框造成的阅读顺序错误。
2. 表格用 Markdown 表格重建；属性、技能百分比、骰子表达式、护甲、理智损失必须逐字逐数保留。
3. 无法辨认的内容写 [无法辨认]；原文与图片冲突且无法判断时保留原文并写 [待核对]。
4. 地图图片提取地名；角色卡图片提取姓名、属性、技能、武器。
只输出 JSON：
{
  "chunks": [{"id": "source-001", "text": "复核后的完整正文", "issues": ["..."], "confidence": "high|medium|low"}],
  "images": [{"page": 12, "type": "map|character|illustration|table", "locations": [], "name": "", "attributes": {}, "skills": {}, "description": ""}]
}
必须返回输入中的每一个 chunk id，不得新增或遗漏。"""


class LLMModuleReviewer:
    """基于 DeepSeek 视觉的模组复核器。"""

    def __init__(
        self,
        vision: VisionClient,
        *,
        batch_chars: int = 24_000,
        max_images_per_batch: int = 8,
    ):
        self.vision = vision
        self.batch_chars = max(2_000, int(batch_chars))
        self.max_images_per_batch = max(0, int(max_images_per_batch))

    def review(self, chunks: list[ModuleSourceChunk], parsed: ParseResult) -> ReviewOutcome:
        warnings: list[str] = []
        corrected: dict[str, ModuleSourceChunk] = {}
        visual_entities: list[dict] = []
        for batch in self._batches(chunks):
            image_paths = self._image_paths(batch, parsed)
            prompt = self._prompt(batch)
            try:
                payload = self.vision.review_chunks(prompt, image_paths)
            except Exception as exc:  # noqa: BLE001 - 单批失败不能丢掉整本
                warnings.append(f"复核批次失败: {type(exc).__name__}: {exc}")
                continue
            items = payload.get("chunks")
            if not isinstance(items, list):
                warnings.append("复核返回缺少 chunks 数组")
                continue
            by_id = {
                str(item.get("id")): item for item in items
                if isinstance(item, dict) and item.get("id")
            }
            for chunk in batch:
                item = by_id.get(chunk.id)
                text = str((item or {}).get("text", "")).strip()
                if not text:
                    warnings.append(f"{chunk.id} 复核结果为空，保留 MinerU 原文")
                    continue
                raw_issues = (item or {}).get("issues") or []
                if not isinstance(raw_issues, list):
                    raw_issues = [str(raw_issues)]
                corrected[chunk.id] = ModuleSourceChunk(
                    id=chunk.id,
                    heading=chunk.heading,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    text=text,
                    raw_text=chunk.raw_text or chunk.text,
                    extraction_method="mineru+deepseek",
                    image_paths=list(chunk.image_paths),
                    review={
                        "model": getattr(self.vision, "model", "deepseek"),
                        "issues": [str(issue) for issue in raw_issues],
                        "confidence": str((item or {}).get("confidence", "")),
                    },
                )
            for item in payload.get("images", []) or []:
                if isinstance(item, dict):
                    visual_entities.append(item)

        result: list[ModuleSourceChunk] = []
        for chunk in chunks:
            result.append(corrected.get(chunk.id, chunk))
        return ReviewOutcome(
            chunks=result,
            visual_entities=visual_entities,
            warnings=warnings,
            status="partial" if warnings else "complete",
        )

    def _batches(self, chunks: list[ModuleSourceChunk]) -> list[list[ModuleSourceChunk]]:
        batches: list[list[ModuleSourceChunk]] = []
        current: list[ModuleSourceChunk] = []
        size = 0
        for chunk in chunks:
            length = len(chunk.heading) + len(chunk.text) + 80
            if current and size + length > self.batch_chars:
                batches.append(current)
                current, size = [], 0
            current.append(chunk)
            size += length
        if current:
            batches.append(current)
        return batches

    def _prompt(self, chunks: list[ModuleSourceChunk]) -> str:
        payload = [
            {
                "id": chunk.id,
                "heading": chunk.heading,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "text": chunk.text,
            }
            for chunk in chunks
        ]
        return REVIEW_PROMPT + "\n\n待复核片段：\n" + json.dumps(payload, ensure_ascii=False)

    def _image_paths(self, chunks: list[ModuleSourceChunk], parsed: ParseResult) -> list[str]:
        if not parsed.images_dir:
            return []
        candidates: list[str] = []
        for chunk in chunks:
            candidates.extend(chunk.image_paths)
        if not candidates:
            # 兼容手工构造的 chunk：按页范围从 ParseResult 回查图片。
            start = min(chunk.page_start for chunk in chunks)
            end = max(chunk.page_end for chunk in chunks)
            candidates.extend(
                block.img_path for block in parsed.blocks
                if block.type == "image" and block.img_path and start <= int(block.page_idx) + 1 <= end
            )
        paths: list[str] = []
        for raw in candidates:
            path = Path(parsed.images_dir) / Path(raw).name
            if path.exists() and str(path) not in paths:
                paths.append(str(path))
        return paths[: self.max_images_per_batch]
