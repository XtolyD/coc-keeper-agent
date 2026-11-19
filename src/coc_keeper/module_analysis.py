# -*- coding: utf-8 -*-
"""Model-assisted semantic analysis for Keeper-only module source material."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from .agent.llm import LLMClient
from .modules import KeeperModule, StoryGraph


ANALYSIS_SYSTEM_PROMPT = """你是《克苏鲁的呼唤》第七版模组结构化编辑器。
输入是 Keeper 私密 PDF 原文。只提取原文明确存在的事实，不补写剧情，不向玩家输出任何内容。
返回一个 JSON 对象，且只能返回 JSON。结构必须为：
{
  "actors": [{
    "id": "actor-...", "name": "...", "kind": "npc|monster", "aliases": [],
    "role": "剧情职责", "description": "外貌与背景", "motivation": "动机",
    "attributes": {"STR": 0, "CON": 0, "SIZ": 0, "DEX": 0, "INT": 0, "APP": 0,
      "POW": 0, "EDU": 0, "SAN": 0, "HP": 0, "MP": 0, "MOV": 0, "BUILD": 0, "DB": ""},
    "skills": {"技能名": 0}, "attacks": [{"name": "", "value": 0, "damage": "", "notes": ""}],
    "armor": "", "sanity_loss": "", "notes": [], "source_pages": []
  }],
  "locations": [{
    "id": "location-...", "name": "...", "description": "稳定的地点信息",
    "atmosphere": "感官氛围", "features": [], "connections": ["location-id"], "source_pages": []
  }],
  "scenes": [{
    "id": "scene-...", "keeper_title": "...", "public_title": "不剧透标题",
    "location_id": "location-id或空", "summary": "该可玩场景的局面，不写未来剧情",
    "atmosphere": "", "entry_conditions": [], "exits": [], "actor_ids": [],
    "clues": [{"id": "clue-...", "name": "", "description": "", "discovery": "如何发现", "skill": "", "leads_to": []}],
    "events": [{"id": "event-...", "title": "", "trigger": "", "description": "",
      "checks": [], "consequences": {"success": "", "failure": ""}, "actor_ids": [], "clue_ids": []}],
    "objectives": [], "secrets": [], "source_chunk_ids": ["source-id"],
    "page_start": 1, "page_end": 1
  }],
  "story": {
    "outline": ["按因果顺序概括主线与可能结局"], "entry_node_id": "node-...",
    "nodes": [{"id": "node-...", "title": "", "scene_id": "scene-id", "kind": "entry|scene|choice|ending",
      "summary": "剧情节点发生什么", "prerequisites": [], "effects": []}],
    "edges": [{"id": "edge-...", "source": "node-id", "target": "node-id", "condition": "进入条件",
      "choice_label": "玩家选择或事件结果", "is_default": false, "secret": false}]
  }
}
要求：
1. 所有有属性块的 NPC 和怪物必须逐个存储；属性、技能、攻击、护甲和理智损失按原文抄录。
2. 场景是玩家可交互的地点/局面；原文中的人物、线索、事件、检定和后果拆成独立字段。
3. 剧情大纲和分支只放在 story；场景不得承担先后顺序。
4. 每个引用 ID 必须真实存在；节点可以引用同一场景以表达不同剧情状态。
5. 不能确定的数据用空字符串、空数组或省略对应属性，绝不猜测。
6. 如果输入同时包含“DeepSeek 复核稿”和“MinerU 原文”，用复核稿确定阅读顺序和表格结构，
   用 MinerU 原文核对专有名词与数值；两者冲突且无法判断时必须保留不确定性，不能自行编造。
7. 每个场景的 source_chunk_ids 只能引用输入中与该场景直接相关的原文片段 ID；不要仅因页码相同引用其他场景的片段。
"""


def _extract_json(text: str) -> dict[str, Any]:
    candidate = str(text or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回可解析的模组 JSON") from None
        value = json.loads(candidate[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回的模组分析不是 JSON 对象")
    return value


class LLMModuleAnalyzer:
    def __init__(
        self,
        client: LLMClient,
        *,
        max_source_chars: int = 1_500_000,
        progress: Callable[[str], None] | None = None,
    ):
        self.client = client
        self.max_source_chars = max(20_000, int(max_source_chars))
        self.progress = progress or (lambda _stage: None)

    def analyze(self, module: KeeperModule) -> KeeperModule:
        source = "\n\n".join(chunk.analysis_text() for chunk in module.source_chunks if chunk.text)
        if not source.strip():
            raise ValueError("模组没有可供分析的 PDF 原文")
        if len(source) > self.max_source_chars:
            raise ValueError(f"模组原文超过深度分析上限 {self.max_source_chars} 字符")
        warnings: list[str] = []
        usages: list[dict[str, int]] = []
        self.progress("正在分析角色与怪物")
        try:
            actor_payload, actor_usage = self._request(
                module, source,
                "只返回顶层键 actors。逐个提取 NPC 和怪物，尤其不能遗漏有属性、技能、攻击、护甲或理智损失的实体。",
            )
            usages.append(actor_usage)
        except Exception as exc:  # noqa: BLE001 - retain deterministic extraction when the provider fails
            actor_payload = {"actors": []}
            warnings.append(f"角色/怪物深度分析回退: {type(exc).__name__}: {exc}")
        actors = self._merge_actors(actor_payload.get("actors", []), [actor.__dict__ for actor in module.actors])
        actor_catalog = [
            {"id": item.get("id"), "name": item.get("name")}
            for item in actors if isinstance(item, dict)
        ]
        scene_payloads: list[dict[str, Any]] = []
        batches = [module.source_chunks[index:index + 2] for index in range(0, len(module.source_chunks), 2)]
        for batch_index, chunks in enumerate(batches, 1):
            self.progress(f"正在分析场景 {batch_index}/{len(batches)}")
            batch_source = "\n\n".join(
                f"【原文片段 {chunk.id}；第 {chunk.page_start}-{chunk.page_end} 页】\n{chunk.analysis_text()}"
                for chunk in chunks if chunk.text
            )
            try:
                batch_payload, batch_usage = self._request(
                    module, batch_source,
                    "只返回顶层键 locations 和 scenes。细分本批原文的可交互地点/局面、线索与事件；"
                    "不要返回 actors 或 story。场景 actor_ids 只能使用以下实体目录中的 ID："
                    + json.dumps(actor_catalog, ensure_ascii=False)
                    + f"。所有地点和场景 ID 必须以 -b{batch_index} 结尾，避免跨批重复。",
                )
                usages.append(batch_usage)
                batch_payload = self._validate_scene_batch(module, batch_payload, actors, chunks)
            except Exception as exc:  # noqa: BLE001 - a single malformed batch must not discard other analysis
                batch_payload = self._fallback_scene_batch(module, chunks)
                warnings.append(f"场景批次 {batch_index} 深度分析回退: {type(exc).__name__}: {exc}")
            scene_payloads.append(batch_payload)
        scene_payload = self._merge_scene_batches(scene_payloads)
        scene_catalog = [
            {"id": item.get("id"), "title": item.get("keeper_title")}
            for item in scene_payload.get("scenes", []) if isinstance(item, dict)
        ]
        story_source = json.dumps({
            "scenes": [
                {key: item.get(key) for key in (
                    "id", "keeper_title", "summary", "entry_conditions", "exits",
                    "clues", "events", "objectives", "secrets",
                )}
                for item in scene_payload.get("scenes", []) if isinstance(item, dict)
            ]
        }, ensure_ascii=False)
        self.progress("正在构建故事线")
        try:
            story_payload, story_usage = self._request(
                module, story_source,
                "只返回顶层键 story。根据以下已经确定的场景 ID 建立大纲、剧情节点和有条件分支，"
                "节点只能引用这些场景：" + json.dumps(scene_catalog, ensure_ascii=False),
            )
            usages.append(story_usage)
        except Exception as exc:  # noqa: BLE001 - linear graph remains safe and editable
            story_payload = {"story": {}}
            warnings.append(f"故事图深度分析回退: {type(exc).__name__}: {exc}")
        payload = {
            "actors": actors,
            "locations": scene_payload.get("locations", []),
            "scenes": scene_payload.get("scenes", []),
            "story": story_payload.get("story", {}),
        }
        try:
            self.progress("正在校验引用")
            refined = self._build_module(module, payload)
        except ValueError as exc:
            warnings.append(f"故事图引用校验回退: {exc}")
            refined = self._build_module(module, {**payload, "story": {}})
        warnings.extend(
            f"场景 {scene.id} 未能唯一关联原文片段，保留结构化信息等待校对"
            for scene in refined.scenes if not scene.source_chunk_ids
        )
        usage = {
            key: sum(int(item.get(key, 0) or 0) for item in usages)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        refined.analysis = {
            **dict(module.analysis),
            "mode": "llm", "status": "partial" if warnings else "complete", "schema": 2,
            "model": self.client.settings.model,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "usage": usage, "stages": ["actors", "scenes", "story"], "warnings": warnings,
        }
        self.progress("分析完成")
        return refined

    @staticmethod
    def _merge_actors(primary: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actors = [dict(item) for item in primary or [] if isinstance(item, dict)]
        names = {str(item.get("name", "")).strip().lower(): index for index, item in enumerate(actors)}
        used_ids = {str(item.get("id", "")) for item in actors}
        for raw in fallback:
            item = dict(raw)
            key = str(item.get("name", "")).strip().lower()
            if key in names:
                current = actors[names[key]]
                current["attributes"] = {**dict(item.get("attributes", {})), **dict(current.get("attributes", {}))}
                current["skills"] = {**dict(item.get("skills", {})), **dict(current.get("skills", {}))}
                for field_name in ("attacks", "armor", "sanity_loss", "source_pages"):
                    if not current.get(field_name) and item.get(field_name):
                        current[field_name] = item[field_name]
                continue
            base_id = str(item.get("id", f"actor-{len(actors) + 1:03d}"))
            candidate = base_id
            suffix = 2
            while candidate in used_ids:
                candidate = f"{base_id}-{suffix}"
                suffix += 1
            item["id"] = candidate
            used_ids.add(candidate)
            names[key] = len(actors)
            actors.append(item)
        return actors

    @staticmethod
    def _fallback_scene_batch(module: KeeperModule, chunks: list[Any]) -> dict[str, list[dict[str, Any]]]:
        chunk_ids = {chunk.id for chunk in chunks}
        scene_items = [
            scene.to_dict() for scene in module.scenes
            if chunk_ids.intersection(scene.source_chunk_ids)
        ]
        location_ids = {str(item.get("location_id", "")) for item in scene_items}
        locations = [location.__dict__ for location in module.locations if location.id in location_ids]
        return {"locations": locations, "scenes": scene_items}

    @classmethod
    def _validate_scene_batch(
        cls,
        module: KeeperModule,
        payload: dict[str, Any],
        actors: list[dict[str, Any]],
        chunks: list[Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Validate one response before it can replace the batch's original scenes."""
        scenes = payload.get("scenes")
        locations = payload.get("locations", [])
        if not isinstance(scenes, list) or not scenes or not all(isinstance(item, dict) for item in scenes):
            raise ValueError("场景批次必须返回非空 scenes 对象数组")
        if not isinstance(locations, list) or not all(isinstance(item, dict) for item in locations):
            raise ValueError("场景批次 locations 必须是对象数组")
        batch_chunk_ids = {chunk.id for chunk in chunks}
        for scene in scenes:
            references = scene.get("source_chunk_ids", [])
            if not isinstance(references, list) or any(item not in batch_chunk_ids for item in references):
                raise ValueError("场景引用了本批次以外或格式无效的原文片段")
        validated = cls._build_module(module, {
            "actors": actors, "locations": locations, "scenes": scenes, "story": {},
        })
        return {
            "locations": [dict(location.__dict__) for location in validated.locations],
            "scenes": [scene.to_dict() for scene in validated.scenes],
        }

    @staticmethod
    def _merge_scene_batches(payloads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        locations: list[dict[str, Any]] = []
        scenes: list[dict[str, Any]] = []
        location_ids: set[str] = set()
        scene_ids: set[str] = set()
        for batch_index, payload in enumerate(payloads, 1):
            location_map: dict[str, str] = {}
            for raw in payload.get("locations", []):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                old_id = str(item.get("id", f"location-{batch_index}"))
                new_id = old_id
                suffix = 2
                while new_id in location_ids:
                    new_id = f"{old_id}-{suffix}"
                    suffix += 1
                item["id"] = new_id
                location_map[old_id] = new_id
                location_ids.add(new_id)
                locations.append(item)
            for raw in payload.get("scenes", []):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                old_id = str(item.get("id", f"scene-{batch_index}"))
                new_id = old_id
                suffix = 2
                while new_id in scene_ids:
                    new_id = f"{old_id}-{suffix}"
                    suffix += 1
                item["id"] = new_id
                if item.get("location_id") in location_map:
                    item["location_id"] = location_map[item["location_id"]]
                scene_ids.add(new_id)
                scenes.append(item)
        return {"locations": locations, "scenes": scenes}

    def _request(
        self,
        module: KeeperModule,
        source: str,
        focus: str,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        response = self.client.chat(
            [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT + "\n\n本阶段要求：" + focus},
                {"role": "user", "content": f"模组：{module.title}\n来源：{module.source_name}\n\nMinerU 原文：\n{source}"},
            ],
            temperature=0.1, max_tokens=12_000, timeout=300.0,
            response_format={"type": "json_object"},
        )
        return _extract_json(response.content or ""), dict(response.usage)

    @staticmethod
    def _build_module(original: KeeperModule, payload: dict[str, Any]) -> KeeperModule:
        scene_items = [deepcopy(item) for item in payload.get("scenes", []) if isinstance(item, dict)]
        location_items = [deepcopy(item) for item in payload.get("locations", []) if isinstance(item, dict)]
        if not scene_items:
            scene_items = [scene.to_dict() for scene in original.scenes]
        chunk_ids = {chunk.id for chunk in original.source_chunks}
        actor_ids = {
            str(item.get("id")) for item in payload.get("actors", [])
            if isinstance(item, dict) and item.get("id")
        }
        location_ids = {
            str(item.get("id")) for item in location_items
            if isinstance(item, dict) and item.get("id")
        }
        for location in location_items:
            location["connections"] = [
                item for item in location.get("connections", []) if item in location_ids
            ]
        for scene in scene_items:
            # Model scene prose is structured analysis, not a new PDF source.
            scene.pop("text", None)
            scene.pop("source_text", None)
            start = int(scene.get("page_start", 0))
            end = int(scene.get("page_end", start))
            references = scene.get("source_chunk_ids", [])
            if not isinstance(references, list) or any(item not in chunk_ids for item in references):
                raise ValueError(f"场景 {scene.get('id', '')} 的原文片段引用无效")
            if references:
                scene["source_chunk_ids"] = list(dict.fromkeys(references))
            else:
                # Page overlap alone cannot separate multiple scenes on a page.
                # Recover only a single whole chunk used by no other scene.
                candidates = [
                    chunk for chunk in original.source_chunks
                    if start <= chunk.page_start and chunk.page_end <= end
                ]
                candidate = candidates[0] if len(candidates) == 1 else None
                shared = candidate is not None and any(
                    other is not scene
                    and int(other.get("page_start", 0)) <= candidate.page_end
                    and int(other.get("page_end", other.get("page_start", 0))) >= candidate.page_start
                    for other in scene_items
                )
                scene["source_chunk_ids"] = [candidate.id] if candidate is not None and not shared else []
            scene["actor_ids"] = [item for item in scene.get("actor_ids", []) if item in actor_ids]
            if scene.get("location_id") not in location_ids:
                scene["location_id"] = ""
            clue_ids = {
                str(item.get("id")) for item in scene.get("clues", [])
                if isinstance(item, dict) and item.get("id")
            }
            for event in scene.get("events", []):
                if not isinstance(event, dict):
                    continue
                event["actor_ids"] = [item for item in event.get("actor_ids", []) if item in actor_ids]
                event["clue_ids"] = [item for item in event.get("clue_ids", []) if item in clue_ids]

        data = {
            "version": 2, "title": original.title, "source_name": original.source_name,
            "actors": payload.get("actors", []), "locations": location_items,
            "source_chunks": [dict(chunk.__dict__) for chunk in original.source_chunks],
            "scenes": scene_items, "story": payload.get("story", {}),
            "analysis": dict(original.analysis),
        }
        try:
            return KeeperModule.from_dict(data)
        except ValueError as exc:
            # A missing graph is recoverable; broken references are not silently accepted.
            if payload.get("story"):
                raise ValueError(f"模型返回的剧情图无效: {exc}") from exc
            partial = KeeperModule.from_dict({**data, "story": {}})
            partial.story = StoryGraph.linear(partial.scenes)
            return partial
