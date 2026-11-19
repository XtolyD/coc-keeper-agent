# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace

import pytest

from coc_keeper.agent.llm import LLMResponse
from coc_keeper.module_analysis import LLMModuleAnalyzer, _extract_json
from coc_keeper.modules import KeeperModule, ModuleRuntime, ModuleScene, ModuleSourceChunk


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
        ModuleScene("scene-local", "本地页块", "当前场景", 1, 2, "===== 第 1 页 =====\n原始 PDF 内容。"),
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
    assert "MinerU 原文" in client.messages[1]["content"]


def test_llm_analysis_falls_back_per_stage_and_remains_loadable():
    original = KeeperModule("旧宅", "house.pdf", [
        ModuleScene("scene-local", "本地场景", "当前场景", 1, 1, "原始内容。"),
    ])
    client = FailingSceneClient({"actors": []})
    analyzed = LLMModuleAnalyzer(client).analyze(original)
    assert analyzed.analysis["status"] == "partial"
    assert len(analyzed.analysis["warnings"]) == 2
    assert analyzed.scenes[0].id == "scene-local"
    assert analyzed.story.entry_node_id
    assert KeeperModule.from_dict(analyzed.to_dict()).title == "旧宅"


def test_same_page_scenes_keep_precise_source_references():
    original = KeeperModule("同页场景", "same-page.pdf", [
        ModuleScene("local-current", "门厅", "门厅", 1, 1, source_chunk_ids=["current"]),
        ModuleScene("local-future", "密室", "密室", 1, 1, source_chunk_ids=["future"]),
    ], source_chunks=[
        ModuleSourceChunk("current", "门厅", 1, 1, "门厅里有一把生锈钥匙。"),
        ModuleSourceChunk("future", "密室", 1, 1, "镇长是守门人，墙后藏着最终仪式。"),
    ])
    payload = {"actors": [], "locations": [], "scenes": [
        {
            "id": "current-scene", "keeper_title": "门厅", "public_title": "门厅",
            "page_start": 1, "page_end": 1, "source_chunk_ids": ["current"],
        },
        {
            "id": "future-scene", "keeper_title": "密室", "public_title": "密室",
            "page_start": 1, "page_end": 1, "source_chunk_ids": ["future"],
        },
    ]}
    refined = LLMModuleAnalyzer._build_module(original, payload)
    runtime = ModuleRuntime(refined)
    assert runtime.current.source_chunk_ids == ["current"]
    assert "生锈钥匙" in str(runtime.keeper_context())
    assert "最终仪式" not in str(runtime.keeper_context())

    for scene in payload["scenes"]:
        scene.pop("source_chunk_ids")
        scene["text"] = "模型提供的场景描述不能冒充 PDF 原文。"
    analyzed = LLMModuleAnalyzer(FakeClient(payload)).analyze(original)
    assert analyzed.analysis["status"] == "partial"
    assert all(scene.source_chunk_ids == [] for scene in analyzed.scenes)
    assert ModuleRuntime(analyzed).keeper_context()["excerpts"] == []


def test_source_fallback_does_not_use_a_chunk_spanning_future_pages():
    original = KeeperModule("跨页原文", "pages.pdf", [
        ModuleScene("local", "页块", "页块", 1, 2, source_chunk_ids=["both-pages"]),
    ], source_chunks=[
        ModuleSourceChunk("both-pages", "原文", 1, 2, "第一页门厅。第二页最终仪式。"),
    ])
    refined = LLMModuleAnalyzer._build_module(original, {"scenes": [{
        "id": "first-page", "keeper_title": "门厅", "public_title": "门厅",
        "page_start": 1, "page_end": 1,
    }]})
    assert refined.scenes[0].source_chunk_ids == []
    assert ModuleRuntime(refined).keeper_context()["excerpts"] == []


@pytest.mark.parametrize("bad_scenes", [
    [{"id": "bad", "keeper_title": "错误页码", "page_start": 9, "page_end": 1}],
    [{"id": "bad", "keeper_title": "未知来源", "source_chunk_ids": ["unknown"]}],
    [{"id": "bad", "keeper_title": "坏线索", "clues": [{"name": "缺少 ID"}]}],
    [{"id": "duplicate"}, {"id": "duplicate"}],
])
def test_invalid_scene_batch_falls_back_without_discarding_valid_batches(bad_scenes):
    original = KeeperModule("多批场景", "batches.pdf", [
        ModuleScene(f"local-{page}", f"原场景 {page}", "当前场景", page, page,
                    source_chunk_ids=[f"source-{page}"])
        for page in range(1, 5)
    ], source_chunks=[
        ModuleSourceChunk(f"source-{page}", f"第 {page} 页", page, page, f"原文 {page}。")
        for page in range(1, 5)
    ])
    good_scene = {
        "id": "refined-b2", "keeper_title": "成功分析的后续场景", "public_title": "后续场景",
        "page_start": 3, "page_end": 4, "source_chunk_ids": ["source-3", "source-4"],
    }

    class BatchClient(FakeClient):
        def __init__(self):
            super().__init__({})
            self.payloads = iter([
                {"actors": []},
                {"locations": [], "scenes": bad_scenes},
                {"locations": [], "scenes": [good_scene]},
                {"story": {}},
            ])
            self.scene_prompts = []

        def chat(self, messages, **kwargs):
            self.payload = next(self.payloads)
            if "原文片段 source-" in messages[1]["content"]:
                self.scene_prompts.append(messages[1]["content"])
            return super().chat(messages, **kwargs)

    client = BatchClient()
    refined = LLMModuleAnalyzer(client).analyze(original)
    assert [scene.id for scene in refined.scenes] == ["local-1", "local-2", "refined-b2"]
    assert refined.scenes[-1].source_chunk_ids == ["source-3", "source-4"]
    assert refined.analysis["status"] == "partial"
    assert len(refined.analysis["warnings"]) == 1
    assert "场景批次 1" in refined.analysis["warnings"][0]
    assert len(client.scene_prompts) == 2
    assert KeeperModule.from_dict(refined.to_dict()).title == original.title
