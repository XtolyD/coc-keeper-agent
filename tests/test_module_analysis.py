# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace

from coc_keeper.agent.llm import LLMResponse
from coc_keeper.module_analysis import LLMModuleAnalyzer, _extract_json
from coc_keeper.modules import KeeperModule, ModuleSection


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.settings = SimpleNamespace(model="analysis-test")
        self.messages = None

    def chat(self, messages, **_kwargs):
        self.messages = messages
        return LLMResponse(
            content="```json\n" + json.dumps(self.payload, ensure_ascii=False) + "\n```",
            usage={"total_tokens": 42},
        )


class FailingSceneClient(FakeClient):
    def __init__(self, actor_payload):
        super().__init__(actor_payload)
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 2:
            raise ValueError("malformed scene JSON")
        if self.calls == 3:
            raise ValueError("malformed story JSON")
        return super().chat(messages, **kwargs)


def test_extract_json_accepts_fenced_payload():
    assert _extract_json('```json\n{"actors": []}\n```') == {"actors": []}


def test_llm_analysis_builds_entities_scenes_and_story_without_losing_source():
    original = KeeperModule("旧宅", "house.pdf", [
        ModuleSection("scene-local", "本地页块", "当前场景", 1, 2, "===== 第 1 页 =====\n原始 PDF 内容。"),
    ])
    payload = {
        "actors": [{
            "id": "actor-doctor", "name": "韦伯医生", "kind": "npc",
            "attributes": {"STR": 40, "HP": 8}, "skills": {"医学": 70},
            "attacks": [], "source_pages": [1],
        }],
        "locations": [{"id": "location-study", "name": "书房", "source_pages": [1]}],
        "scenes": [{
            "id": "scene-study", "keeper_title": "调查书房", "public_title": "书房",
            "location_id": "location-study", "summary": "调查医生遗物。", "actor_ids": ["actor-doctor"],
            "clues": [], "events": [], "objectives": ["找到日记"], "secrets": ["医生隐瞒了仪式"],
            "page_start": 1, "page_end": 2,
        }],
        "story": {
            "outline": ["调查书房", "发现日记"], "entry_node_id": "node-study",
            "nodes": [{"id": "node-study", "title": "调查", "scene_id": "scene-study", "kind": "entry"}],
            "edges": [],
        },
    }
    client = FakeClient(payload)
    analyzed = LLMModuleAnalyzer(client).analyze(original)
    assert analyzed.actors[0].attributes["HP"] == 8
    assert analyzed.scenes[0].source_chunk_ids == ["source-001"]
    assert analyzed.scene_text(analyzed.scenes[0]).endswith("原始 PDF 内容。")
    assert analyzed.story.outline == ["调查书房", "发现日记"]
    assert analyzed.analysis["status"] == "complete"
    assert "PDF 原文" in client.messages[1]["content"]


def test_llm_analysis_falls_back_per_stage_and_remains_loadable():
    original = KeeperModule("旧宅", "house.pdf", [
        ModuleSection("scene-local", "本地场景", "当前场景", 1, 1, "原始内容。"),
    ])
    client = FailingSceneClient({"actors": []})
    analyzed = LLMModuleAnalyzer(client).analyze(original)
    assert analyzed.analysis["status"] == "partial"
    assert len(analyzed.analysis["warnings"]) == 2
    assert analyzed.scenes[0].id == "scene-local"
    assert analyzed.story.entry_node_id
    assert KeeperModule.from_dict(analyzed.to_dict()).title == "旧宅"
