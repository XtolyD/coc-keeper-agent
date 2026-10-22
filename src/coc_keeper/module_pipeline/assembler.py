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


def _page_number(value: object) -> int:
    try:
        page = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return page if page > 0 else 0


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
        max_page = max((chunk.page_end for chunk in chunks), default=0)
        reviewed_pages = [""] * max_page
        for chunk in chunks:
            if not chunk.text:
                continue
            index = max(0, chunk.page_start - 1)
            if index < len(reviewed_pages):
                reviewed_pages[index] = "\n".join(filter(None, [reviewed_pages[index], chunk.text]))
        if any(reviewed_pages):
            raw_sets.append(extract_stat_blocks(reviewed_pages))
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
            if not isinstance(item, dict):
                continue
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
                attributes = item.get("attributes")
                if isinstance(attributes, dict):
                    actor.attributes.update({
                        str(key).upper(): value for key, value in attributes.items()
                    })
                skills = item.get("skills")
                if isinstance(skills, dict):
                    actor.skills.update({str(key): value for key, value in skills.items()})
                if item.get("description"):
                    actor.description = str(item["description"])
                page = _page_number(item.get("page"))
                if page:
                    actor.source_pages = sorted(set(actor.source_pages + [page]))
            elif kind == "map":
                raw_names = item.get("locations")
                if not isinstance(raw_names, list):
                    continue
                for raw_name in raw_names:
                    name = str(raw_name).strip()
                    if not name or name.lower() in known_locations:
                        continue
                    page = _page_number(item.get("page"))
                    location = ModuleLocation(
                        id=f"location-{len(locations) + 1:03d}",
                        name=name,
                        description=str(item.get("description", "")),
                        source_pages=[page] if page else [],
                    )
                    locations.append(location)
                    known_locations[name.lower()] = location
