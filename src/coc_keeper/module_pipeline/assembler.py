# -*- coding: utf-8 -*-
"""把 MinerU 原文与 DeepSeek 复核结果组装为 KeeperModule。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..docparser.result import ParseResult
from ..modules import (
    KeeperModule, ModuleActor, ModuleLocation, ModuleScene, ModuleSourceChunk, StoryGraph,
)
from .ingest import source_page_texts
from .ports import ReviewOutcome
from .stat_extractor import extract_stat_blocks, infer_title, merge_local_actors


class ModuleAssembler:
    """无状态组装器：source chunks → v2 模组结构。"""

    def build(
        self,
        parsed: ParseResult,
        chunks: list[ModuleSourceChunk],
        review: ReviewOutcome | None = None,
        *,
        title: str | None = None,
    ) -> KeeperModule:
        if not chunks:
            raise ValueError("MinerU 没有产出可用的模组原文")
        final_chunks = list(review.chunks) if review and review.chunks else list(chunks)
        page_texts = source_page_texts(parsed)
        inferred_title = title or infer_title(page_texts, Path(parsed.source_pdf).stem)

        locations: list[ModuleLocation] = []
        scenes: list[ModuleScene] = []
        for index, chunk in enumerate(final_chunks, 1):
            heading = chunk.heading or f"第 {chunk.page_start} 页"
            summary = KeeperModule._summarize(chunk.text, fallback=heading)
            location_id = f"location-{index:03d}"
            locations.append(ModuleLocation(
                id=location_id,
                name=heading,
                description=summary,
                source_pages=list(range(chunk.page_start, chunk.page_end + 1)),
            ))
            scenes.append(ModuleScene(
                id=f"scene-{index:03d}",
                keeper_title=heading,
                public_title="当前场景",
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                location_id=location_id,
                summary=summary,
                source_chunk_ids=[chunk.id],
            ))

        actors = self._actors(page_texts, final_chunks, review)
        self._merge_visual_entities(review, actors, locations)
        return KeeperModule(
            title=inferred_title,
            source_name=Path(parsed.source_pdf).name,
            scenes=scenes,
            actors=actors,
            locations=locations,
            source_chunks=final_chunks,
            story=StoryGraph.linear(scenes),
            analysis={
                "mode": "mineru+deepseek" if review else "mineru",
                "status": "needs-review",
                "schema": 2,
                "mineru": {
                    "parsed_at": parsed.parsed_at,
                    "blocks": len(parsed.blocks),
                    "images": str(parsed.images_dir or ""),
                },
                "review": {
                    "status": review.status if review else "skipped",
                    "warnings": list(review.warnings) if review else [],
                    "usage": dict(review.usage) if review else {},
                },
                "visual_entities": list(review.visual_entities) if review else [],
                "assembled_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _actors(
        page_texts: list[str],
        chunks: list[ModuleSourceChunk],
        review: ReviewOutcome | None,
    ) -> list[ModuleActor]:
        raw_sets = [extract_stat_blocks(page_texts)]
        reviewed_text = [chunk.text for chunk in chunks if chunk.text]
        if reviewed_text:
            raw_sets.append(extract_stat_blocks(["\n".join(reviewed_text)]))
        return merge_local_actors(raw_sets)

    @staticmethod
    def _merge_visual_entities(
        review: ReviewOutcome | None,
        actors: list[ModuleActor],
        locations: list[ModuleLocation],
    ) -> None:
        if not review:
            return
        by_name = {actor.name.strip().lower(): actor for actor in actors}
        known_locations = {location.name.strip().lower(): location for location in locations}
        for item in review.visual_entities:
            kind = str(item.get("type", "")).lower()
            if kind == "character":
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                actor = by_name.get(name.lower())
                if actor is None:
                    actor = ModuleActor(id=f"actor-{len(actors) + 1:03d}", name=name)
                    actors.append(actor)
                    by_name[name.lower()] = actor
                actor.attributes.update({
                    str(key).upper(): value for key, value in dict(item.get("attributes", {})).items()
                })
                actor.skills.update({
                    str(key): value for key, value in dict(item.get("skills", {})).items()
                })
                if item.get("description"):
                    actor.description = str(item["description"])
                if item.get("page"):
                    actor.source_pages = sorted(set(actor.source_pages + [int(item["page"])]))
            elif kind == "map":
                for raw_name in item.get("locations", []) or []:
                    name = str(raw_name).strip()
                    if not name or name.lower() in known_locations:
                        continue
                    location = ModuleLocation(
                        id=f"location-{len(locations) + 1:03d}",
                        name=name,
                        description=str(item.get("description", "")),
                        source_pages=[int(item["page"])] if item.get("page") else [],
                    )
                    locations.append(location)
                    known_locations[name.lower()] = location
