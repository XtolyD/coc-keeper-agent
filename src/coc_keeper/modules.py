# -*- coding: utf-8 -*-
"""Structured PDF module storage, graph progression, and spoiler isolation."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .retrieval import Index, search


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _int_list(value: Any) -> list[int]:
    result: list[int] = []
    for item in value or []:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


@dataclass
class ModuleSourceChunk:
    """Traceable MinerU source content. Gameplay scenes reference chunks, not plot prose."""

    id: str
    heading: str
    page_start: int
    page_end: int
    text: str
    raw_text: str = ""
    extraction_method: str = "mineru"
    image_paths: list[str] = field(default_factory=list)
    review: dict[str, Any] = field(default_factory=dict)

    def analysis_text(self) -> str:
        """给分析器同时提供复核稿与 MinerU 原文，供交叉核对。"""
        if self.raw_text.strip() and self.raw_text.strip() != self.text.strip():
            return f"【DeepSeek 复核稿】\n{self.text}\n\n【MinerU 原文】\n{self.raw_text}".strip()
        return self.text

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleSourceChunk":
        method = str(data.get("extraction_method", "mineru"))
        if method == "hybrid-vision":
            raise ValueError("旧版 hybrid-vision 模组不再支持，请删除后重新导入 PDF")
        return cls(
            id=str(data["id"]), heading=str(data.get("heading", "原文")),
            page_start=int(data.get("page_start", 0)), page_end=int(data.get("page_end", 0)),
            text=str(data.get("text", "")),
            raw_text=str(data.get("raw_text", "")),
            extraction_method=method,
            image_paths=_string_list(data.get("image_paths")),
            review=dict(data.get("review", {})),
        )


@dataclass
class ModuleActor:
    """An independently stored NPC or monster, including any supplied game statistics."""

    id: str
    name: str
    kind: str = "npc"
    aliases: list[str] = field(default_factory=list)
    role: str = ""
    description: str = ""
    motivation: str = ""
    attributes: dict[str, int | str] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    attacks: list[dict[str, Any]] = field(default_factory=list)
    armor: str = ""
    sanity_loss: str = ""
    notes: list[str] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleActor":
        attributes: dict[str, int | str] = {}
        for key, value in dict(data.get("attributes", {})).items():
            try:
                attributes[str(key).upper()] = int(value)
            except (TypeError, ValueError):
                attributes[str(key).upper()] = str(value)
        skills: dict[str, int] = {}
        for key, value in dict(data.get("skills", {})).items():
            try:
                skills[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return cls(
            id=str(data["id"]), name=str(data.get("name", data["id"])),
            kind=str(data.get("kind", "npc")), aliases=_string_list(data.get("aliases")),
            role=str(data.get("role", "")), description=str(data.get("description", "")),
            motivation=str(data.get("motivation", "")), attributes=attributes, skills=skills,
            attacks=[dict(item) for item in data.get("attacks", []) if isinstance(item, dict)],
            armor=str(data.get("armor", "")), sanity_loss=str(data.get("sanity_loss", "")),
            notes=_string_list(data.get("notes")), source_pages=_int_list(data.get("source_pages")),
        )


@dataclass
class ModuleLocation:
    id: str
    name: str
    description: str = ""
    atmosphere: str = ""
    features: list[str] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleLocation":
        return cls(
            id=str(data["id"]), name=str(data.get("name", data["id"])),
            description=str(data.get("description", "")), atmosphere=str(data.get("atmosphere", "")),
            features=_string_list(data.get("features")), connections=_string_list(data.get("connections")),
            source_pages=_int_list(data.get("source_pages")),
        )


@dataclass
class ModuleClue:
    id: str
    name: str
    description: str = ""
    discovery: str = ""
    skill: str = ""
    leads_to: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleClue":
        return cls(
            id=str(data["id"]), name=str(data.get("name", data["id"])),
            description=str(data.get("description", "")), discovery=str(data.get("discovery", "")),
            skill=str(data.get("skill", "")), leads_to=_string_list(data.get("leads_to")),
        )


@dataclass
class ModuleEvent:
    id: str
    title: str
    trigger: str = ""
    description: str = ""
    checks: list[str] = field(default_factory=list)
    consequences: dict[str, str] = field(default_factory=dict)
    actor_ids: list[str] = field(default_factory=list)
    clue_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleEvent":
        return cls(
            id=str(data["id"]), title=str(data.get("title", data["id"])),
            trigger=str(data.get("trigger", "")), description=str(data.get("description", "")),
            checks=_string_list(data.get("checks")),
            consequences={str(key): str(value) for key, value in dict(data.get("consequences", {})).items()},
            actor_ids=_string_list(data.get("actor_ids")), clue_ids=_string_list(data.get("clue_ids")),
        )


@dataclass
class ModuleScene:
    """A playable place/state. Plot ordering lives in StoryGraph, not in this object."""

    # The first six fields retain the old ModuleSection constructor contract.
    id: str
    keeper_title: str
    public_title: str
    page_start: int
    page_end: int
    text: str = field(default="", repr=False)
    location_id: str = ""
    summary: str = ""
    atmosphere: str = ""
    entry_conditions: list[str] = field(default_factory=list)
    exits: list[str] = field(default_factory=list)
    actor_ids: list[str] = field(default_factory=list)
    clues: list[ModuleClue] = field(default_factory=list)
    events: list[ModuleEvent] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    source_chunk_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "keeper_title": self.keeper_title, "public_title": self.public_title,
            "location_id": self.location_id, "summary": self.summary, "atmosphere": self.atmosphere,
            "entry_conditions": list(self.entry_conditions), "exits": list(self.exits),
            "actor_ids": list(self.actor_ids), "clues": [asdict(item) for item in self.clues],
            "events": [asdict(item) for item in self.events], "objectives": list(self.objectives),
            "secrets": list(self.secrets), "source_chunk_ids": list(self.source_chunk_ids),
            "page_start": self.page_start, "page_end": self.page_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleScene":
        return cls(
            id=str(data["id"]), keeper_title=str(data.get("keeper_title", data.get("title", data["id"]))),
            public_title=str(data.get("public_title", "当前场景")),
            page_start=int(data.get("page_start", 0)), page_end=int(data.get("page_end", 0)),
            text=str(data.get("text", data.get("source_text", ""))),
            location_id=str(data.get("location_id", "")), summary=str(data.get("summary", "")),
            atmosphere=str(data.get("atmosphere", "")),
            entry_conditions=_string_list(data.get("entry_conditions")), exits=_string_list(data.get("exits")),
            actor_ids=_string_list(data.get("actor_ids")),
            clues=[ModuleClue.from_dict(item) for item in data.get("clues", [])],
            events=[ModuleEvent.from_dict(item) for item in data.get("events", [])],
            objectives=_string_list(data.get("objectives")), secrets=_string_list(data.get("secrets")),
            source_chunk_ids=_string_list(data.get("source_chunk_ids")),
        )


@dataclass
class StoryNode:
    id: str
    title: str
    scene_id: str
    kind: str = "scene"
    summary: str = ""
    prerequisites: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryNode":
        return cls(
            id=str(data["id"]), title=str(data.get("title", data["id"])),
            scene_id=str(data.get("scene_id", "")), kind=str(data.get("kind", "scene")),
            summary=str(data.get("summary", "")), prerequisites=_string_list(data.get("prerequisites")),
            effects=_string_list(data.get("effects")),
        )


@dataclass
class StoryEdge:
    id: str
    source: str
    target: str
    condition: str = ""
    choice_label: str = ""
    is_default: bool = False
    secret: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryEdge":
        return cls(
            id=str(data["id"]), source=str(data["source"]), target=str(data["target"]),
            condition=str(data.get("condition", "")), choice_label=str(data.get("choice_label", "")),
            is_default=bool(data.get("is_default", False)), secret=bool(data.get("secret", False)),
        )


@dataclass
class StoryGraph:
    outline: list[str] = field(default_factory=list)
    entry_node_id: str = ""
    nodes: list[StoryNode] = field(default_factory=list)
    edges: list[StoryEdge] = field(default_factory=list)

    @classmethod
    def linear(cls, scenes: list[ModuleScene]) -> "StoryGraph":
        nodes = [
            StoryNode(f"node-{index:03d}", scene.keeper_title, scene.id, summary=scene.summary)
            for index, scene in enumerate(scenes, 1)
        ]
        edges = [
            StoryEdge(
                f"edge-{index:03d}", nodes[index - 1].id, nodes[index].id,
                condition="当前场景目标已完成", choice_label="继续推进", is_default=True,
            )
            for index in range(1, len(nodes))
        ]
        return cls(
            outline=[scene.summary or scene.keeper_title for scene in scenes],
            entry_node_id=nodes[0].id if nodes else "", nodes=nodes, edges=edges,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryGraph":
        return cls(
            outline=_string_list(data.get("outline")), entry_node_id=str(data.get("entry_node_id", "")),
            nodes=[StoryNode.from_dict(item) for item in data.get("nodes", [])],
            edges=[StoryEdge.from_dict(item) for item in data.get("edges", [])],
        )


def _text_to_chunks(text: str, default_page: int) -> list[dict]:
    """把场景原文按 MinerU 页标记切成可检索块（零外部服务）。"""
    pattern = re.compile(r"=====\s*第\s*(\d+)\s*页\s*=====")
    matches = list(pattern.finditer(text))
    chunks: list[dict] = []
    if not matches:
        body = text.strip()
        return [{
            "name": "", "text": body, "page": default_page,
            "start_page": default_page, "end_page": default_page,
            "path": "", "lines": body.splitlines(),
        }] if body else []
    for index, match in enumerate(matches):
        page = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if not body:
            continue
        chunks.append({
            "name": "", "text": body, "page": page,
            "start_page": page, "end_page": page,
            "path": "", "lines": body.splitlines(),
        })
    return chunks


@dataclass
class KeeperModule:
    title: str
    source_name: str
    scenes: list[ModuleScene]
    actors: list[ModuleActor] = field(default_factory=list)
    locations: list[ModuleLocation] = field(default_factory=list)
    source_chunks: list[ModuleSourceChunk] = field(default_factory=list)
    story: StoryGraph = field(default_factory=StoryGraph)
    analysis: dict[str, Any] = field(default_factory=dict)
    version: int = 2

    def __post_init__(self) -> None:
        if not self.scenes:
            raise ValueError("模组至少需要一个场景")
        chunk_ids = {chunk.id for chunk in self.source_chunks}
        for index, scene in enumerate(self.scenes, 1):
            if scene.text and not scene.source_chunk_ids:
                chunk_id = f"source-{index:03d}"
                while chunk_id in chunk_ids:
                    chunk_id += "-legacy"
                self.source_chunks.append(ModuleSourceChunk(
                    chunk_id, scene.keeper_title, scene.page_start, scene.page_end, scene.text,
                ))
                scene.source_chunk_ids = [chunk_id]
                chunk_ids.add(chunk_id)
            if not scene.summary:
                scene.summary = self._summarize(self.scene_text(scene), fallback=scene.keeper_title)
        if not self.story.nodes:
            self.story = StoryGraph.linear(self.scenes)
        self._validate_references()
        self.version = 2

    @property
    def sections(self) -> list[ModuleScene]:
        """Compatibility alias. New JSON uses ``scenes`` and separate ``source_chunks``."""
        return self.scenes

    @staticmethod
    def _summarize(text: str, *, fallback: str) -> str:
        cleaned = re.sub(r"=====\s*第\s*\d+\s*页\s*=====", "", str(text))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:240] or fallback

    def scene_text(self, scene: ModuleScene) -> str:
        chunks = {chunk.id: chunk for chunk in self.source_chunks}
        selected = [chunks[item] for item in scene.source_chunk_ids if item in chunks]
        if selected:
            return "\n".join(chunk.text for chunk in selected if chunk.text).strip()
        return scene.text

    def _validate_references(self) -> None:
        scene_ids = {scene.id for scene in self.scenes}
        actor_ids = {actor.id for actor in self.actors}
        location_ids = {location.id for location in self.locations}
        chunk_ids = {chunk.id for chunk in self.source_chunks}
        if any(not item for item in scene_ids | actor_ids | location_ids | chunk_ids):
            raise ValueError("模组实体 ID 不能为空")
        if len(scene_ids) != len(self.scenes):
            raise ValueError("场景 ID 不能重复")
        if len(actor_ids) != len(self.actors):
            raise ValueError("角色/怪物 ID 不能重复")
        if len(location_ids) != len(self.locations):
            raise ValueError("地点 ID 不能重复")
        if len(chunk_ids) != len(self.source_chunks):
            raise ValueError("原文片段 ID 不能重复")
        for chunk in self.source_chunks:
            if chunk.page_end < chunk.page_start:
                raise ValueError(f"原文片段 {chunk.id} 的结束页不能小于起始页")
        for location in self.locations:
            missing_connections = [item for item in location.connections if item not in location_ids]
            if missing_connections:
                raise ValueError(f"地点 {location.id} 引用了不存在的连接地点: {'、'.join(missing_connections)}")
        for scene in self.scenes:
            if not scene.keeper_title.strip() or not scene.public_title.strip():
                raise ValueError(f"场景 {scene.id} 的标题不能为空")
            if scene.page_end < scene.page_start:
                raise ValueError(f"场景 {scene.id} 的结束页不能小于起始页")
            if scene.location_id and scene.location_id not in location_ids:
                raise ValueError(f"场景 {scene.id} 引用了不存在的地点 {scene.location_id}")
            missing_actors = [item for item in scene.actor_ids if item not in actor_ids]
            if missing_actors:
                raise ValueError(f"场景 {scene.id} 引用了不存在的角色/怪物: {'、'.join(missing_actors)}")
            missing_chunks = [item for item in scene.source_chunk_ids if item not in chunk_ids]
            if missing_chunks:
                raise ValueError(f"场景 {scene.id} 引用了不存在的原文片段: {'、'.join(missing_chunks)}")
            clue_ids = {clue.id for clue in scene.clues}
            event_ids = {event.id for event in scene.events}
            if len(clue_ids) != len(scene.clues) or len(event_ids) != len(scene.events):
                raise ValueError(f"场景 {scene.id} 的线索或事件 ID 不能重复")
            for event in scene.events:
                missing_event_actors = [item for item in event.actor_ids if item not in actor_ids]
                missing_event_clues = [item for item in event.clue_ids if item not in clue_ids]
                if missing_event_actors or missing_event_clues:
                    raise ValueError(f"场景 {scene.id} 的事件 {event.id} 存在无效引用")
        node_ids = {node.id for node in self.story.nodes}
        if len(node_ids) != len(self.story.nodes):
            raise ValueError("剧情节点 ID 不能重复")
        edge_ids = {edge.id for edge in self.story.edges}
        if len(edge_ids) != len(self.story.edges):
            raise ValueError("剧情分支 ID 不能重复")
        if self.story.entry_node_id not in node_ids:
            raise ValueError("剧情入口节点不存在")
        for node in self.story.nodes:
            if node.scene_id not in scene_ids:
                raise ValueError(f"剧情节点 {node.id} 引用了不存在的场景 {node.scene_id}")
        for edge in self.story.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"剧情分支 {edge.id} 引用了不存在的节点")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 2, "title": self.title, "source_name": self.source_name,
            "actors": [asdict(item) for item in self.actors],
            "locations": [asdict(item) for item in self.locations],
            "source_chunks": [asdict(item) for item in self.source_chunks],
            "scenes": [scene.to_dict() for scene in self.scenes],
            "story": asdict(self.story), "analysis": dict(self.analysis),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeeperModule":
        if "scenes" not in data:
            raise ValueError("旧版 sections 模组不再支持，请删除后重新导入 PDF")
        scenes = [ModuleScene.from_dict(item) for item in data.get("scenes", [])]
        analysis = dict(data.get("analysis", {}))
        return cls(
            title=str(data.get("title", "未命名模组")), source_name=str(data.get("source_name", "")),
            scenes=scenes, actors=[ModuleActor.from_dict(item) for item in data.get("actors", [])],
            locations=[ModuleLocation.from_dict(item) for item in data.get("locations", [])],
            source_chunks=[ModuleSourceChunk.from_dict(item) for item in data.get("source_chunks", [])],
            story=StoryGraph.from_dict(data.get("story", {})), analysis=analysis,
        )

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "KeeperModule":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class ModuleRuntime:
    module: KeeperModule
    current_index: int = 0
    completed: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    current_node_id: str | None = None
    completed_nodes: list[str] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.current_node_id:
            index = max(0, min(int(self.current_index), len(self.module.story.nodes) - 1))
            self.current_node_id = self.module.story.nodes[index].id
        self._sync_index()

    def _sync_index(self) -> None:
        node_ids = [node.id for node in self.module.story.nodes]
        if self.current_node_id not in node_ids:
            self.current_node_id = self.module.story.entry_node_id
        self.current_index = node_ids.index(self.current_node_id)

    @property
    def current_node(self) -> StoryNode:
        return next(node for node in self.module.story.nodes if node.id == self.current_node_id)

    @property
    def current(self) -> ModuleScene:
        scene_id = self.current_node.scene_id
        return next(scene for scene in self.module.scenes if scene.id == scene_id)

    @property
    def available_edges(self) -> list[StoryEdge]:
        return [edge for edge in self.module.story.edges if edge.source == self.current_node_id]

    @property
    def finished(self) -> bool:
        return not self.available_edges and self.current_node_id in self.completed_nodes

    def status(self, *, player_safe: bool = True) -> dict[str, Any]:
        if player_safe:
            return {"module": self.module.title}
        return {
            "module": self.module.title, "scene": self.current.keeper_title,
            "node": self.current_node.title, "finished": self.finished,
            "pages": [self.current.page_start, self.current.page_end],
            "objectives": list(self.current.objectives),
            "branches": [
                {"node_id": edge.target, "choice": edge.choice_label, "condition": edge.condition}
                for edge in self.available_edges
            ],
        }

    def keeper_context(self, query: str = "", *, limit: int = 3, max_chars: int = 8000) -> dict[str, Any]:
        scene = self.current
        text = self.module.scene_text(scene)
        hits = []
        if query.strip() and text:
            chunks = _text_to_chunks(text, scene.page_start)
            hits = search(Index.build(chunks), query, top_k=limit)
        excerpts = [
            {"page": hit.page, "text": hit.text[:2000], "score": round(hit.score, 4)}
            for hit in hits
        ]
        if not excerpts and text:
            excerpts = [{"page": scene.page_start, "text": text[:max_chars], "score": 0.0}]
        actors = {actor.id: actor for actor in self.module.actors}
        locations = {location.id: location for location in self.module.locations}
        return {
            "module": self.module.title,
            "current_scene": {
                "title": scene.keeper_title, "public_title": scene.public_title,
                "summary": scene.summary, "atmosphere": scene.atmosphere,
                "entry_conditions": list(scene.entry_conditions), "exits": list(scene.exits),
                "objectives": list(scene.objectives), "clues": [asdict(item) for item in scene.clues],
                "events": [asdict(item) for item in scene.events],
            },
            "location": asdict(locations[scene.location_id]) if scene.location_id in locations else None,
            "actors": [asdict(actors[item]) for item in scene.actor_ids if item in actors],
            "story": {
                "current_node": asdict(self.current_node),
                "available_branches": [
                    {"target_node_id": edge.target, "choice": edge.choice_label, "condition": edge.condition}
                    for edge in self.available_edges
                ],
            },
            "excerpts": excerpts,
            "discipline": "只能使用当前场景、当前出场实体和已发生事件；不得透露其他节点、分支秘密或完整大纲。",
        }

    def advance(
        self,
        reason: str,
        completed_objectives: list[str] | None = None,
        next_node_id: str | None = None,
    ) -> dict[str, Any]:
        completed_objectives = completed_objectives or []
        missing = [item for item in self.current.objectives if item not in completed_objectives]
        if missing:
            raise ValueError("当前场景目标尚未完成: " + "、".join(missing))
        if not str(reason).strip():
            raise ValueError("推进剧情必须说明已发生的游戏内原因")
        edges = self.available_edges
        selected: StoryEdge | None = None
        if next_node_id:
            selected = next((edge for edge in edges if edge.target == next_node_id), None)
            if selected is None:
                raise ValueError(f"节点 {next_node_id} 不是当前剧情的可用分支")
        elif len(edges) == 1:
            selected = edges[0]
        elif len(edges) > 1:
            defaults = [edge for edge in edges if edge.is_default]
            if len(defaults) == 1:
                selected = defaults[0]
            else:
                raise ValueError("当前剧情存在多个分支，必须指定 next_node_id")
        if self.current.id not in self.completed:
            self.completed.append(self.current.id)
        if self.current_node_id not in self.completed_nodes:
            self.completed_nodes.append(self.current_node_id)
        history_item: dict[str, Any] = {
            "node": self.current_node_id, "scene": self.current.id, "reason": str(reason).strip(),
        }
        if selected:
            history_item["edge"] = selected.id
            history_item["target"] = selected.target
            self.current_node_id = selected.target
            self._sync_index()
        self.history.append(history_item)
        return self.status(player_safe=False)

    def detects_spoiler(self, output: str) -> bool:
        normalized = self._normalize(output)
        if not normalized:
            return False
        completed_scene_ids = set(self.completed) | {self.current.id}
        for scene in self.module.scenes:
            if scene.id in completed_scene_ids:
                continue
            if any(self._normalize(secret) in normalized for secret in scene.secrets if self._normalize(secret)):
                return True
            for sentence in re.split(r"[。！？!?\n]", self.module.scene_text(scene)):
                future = self._normalize(sentence)
                if len(future) < 16:
                    continue
                for start in range(0, len(future) - 15, 8):
                    if future[start:start + 16] in normalized:
                        return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\W+", "", str(text), flags=re.UNICODE).lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module.to_dict(), "current_index": self.current_index,
            "current_node_id": self.current_node_id, "completed": list(self.completed),
            "completed_nodes": list(self.completed_nodes), "history": list(self.history),
            "variables": dict(self.variables),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleRuntime":
        module = KeeperModule.from_dict(data["module"])
        current_node_id = data.get("current_node_id")
        current_index = int(data.get("current_index", 0))
        return cls(
            module=module, current_index=current_index, completed=list(data.get("completed", [])),
            history=list(data.get("history", [])), current_node_id=str(current_node_id) if current_node_id else None,
            completed_nodes=list(data.get("completed_nodes", [])), variables=dict(data.get("variables", {})),
        )
