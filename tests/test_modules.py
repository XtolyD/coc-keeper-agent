# -*- coding: utf-8 -*-
import pytest

from coc_keeper.modules import (
    KeeperModule, ModuleActor, ModuleEvent, ModuleLocation, ModuleRuntime,
    ModuleScene, StoryEdge, StoryGraph, StoryNode,
)
from coc_keeper.module_store import ModuleStore


def make_runtime():
    return ModuleRuntime(KeeperModule("测试模组", "test.pdf", [
        ModuleScene("scene-001", "门厅", "场景 1", 1, 1, "门厅里有一把生锈钥匙。", objectives=["找到钥匙"]),
        ModuleScene(
            "scene-002", "地下祭坛", "场景 2", 2, 2,
            "地下祭坛的守门人其实是镇长，墙后藏着最终仪式。", secrets=["镇长是守门人"],
        ),
    ]))


def test_runtime_hides_future_and_enforces_order():
    runtime = make_runtime()
    assert runtime.status(player_safe=True) == {"module": "测试模组"}
    context = runtime.keeper_context("镇长")
    serialized = str(context)
    assert "生锈钥匙" in serialized
    assert "最终仪式" not in serialized
    with pytest.raises(ValueError):
        runtime.advance("玩家离开门厅", [])
    runtime.advance("玩家找到钥匙并打开门", ["找到钥匙"])
    assert runtime.current.id == "scene-002"


def test_spoiler_gate_and_runtime_roundtrip():
    runtime = make_runtime()
    assert runtime.detects_spoiler("我直接告诉你：镇长是守门人。") is True
    assert runtime.detects_spoiler("门厅里只有一把生锈钥匙。") is False
    restored = ModuleRuntime.from_dict(runtime.to_dict())
    assert restored.module.title == "测试模组"
    assert restored.current.id == "scene-001"


def test_module_store_can_update_and_delete(tmp_path):
    store = ModuleStore(tmp_path / "modules")
    record = store.add(make_runtime().module)
    updated = KeeperModule("修订模组", "revised.pdf", [
        ModuleScene("scene-new", "修订场景", "当前地点", 3, 4, "修订后的 Keeper 原文。"),
    ])
    store.save(record.id, updated)
    assert store.get(record.id).module.title == "修订模组"
    store.delete(record.id)
    assert store.list() == []


def test_module_store_preserves_and_deletes_source_pdf(tmp_path):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF-1.4\n% fake module pdf\n")
    store = ModuleStore(tmp_path / "modules")
    record = store.create(make_runtime().module, source_pdf=path)
    stored_pdf = store.source_pdf_path(record.id)
    assert stored_pdf is not None
    assert stored_pdf.read_bytes() == path.read_bytes()
    store.delete(record.id)
    assert not stored_pdf.exists()


def test_old_schema_and_hybrid_vision_are_rejected():
    with pytest.raises(ValueError, match="旧版 sections"):
        KeeperModule.from_dict({"version": 1, "title": "旧模组", "sections": []})
    with pytest.raises(ValueError, match="hybrid-vision"):
        KeeperModule.from_dict({
            "version": 2, "title": "旧模组", "scenes": [],
            "source_chunks": [{
                "id": "source-001", "heading": "旧", "page_start": 1, "page_end": 1,
                "text": "旧视觉校正", "extraction_method": "hybrid-vision",
            }],
        })


def test_structured_context_resolves_current_scene_entities():
    actor = ModuleActor("actor-doctor", "韦伯医生", role="线索提供者", attributes={"HP": 8})
    location = ModuleLocation("location-study", "医生书房", features=["上锁的抽屉"])
    scene = ModuleScene(
        "scene-study", "书房调查", "书房", 3, 4, location_id=location.id,
        summary="调查书房。", actor_ids=[actor.id],
        events=[ModuleEvent("event-drawer", "打开抽屉", trigger="成功开锁")],
    )
    runtime = ModuleRuntime(KeeperModule(
        "旧宅", "house.pdf", [scene], actors=[actor], locations=[location],
    ))
    context = runtime.keeper_context("抽屉")
    assert context["actors"][0]["name"] == "韦伯医生"
    assert context["location"]["name"] == "医生书房"
    assert context["current_scene"]["events"][0]["id"] == "event-drawer"


def test_story_graph_branch_selection_and_roundtrip():
    scenes = [
        ModuleScene("scene-entry", "入口", "入口", 1, 1, "入口。"),
        ModuleScene("scene-cellar", "地下室", "地下室", 2, 2, "地下室。"),
        ModuleScene("scene-road", "公路", "公路", 3, 3, "公路。"),
    ]
    graph = StoryGraph(
        outline=["进入旧宅", "调查地下室或逃向公路"], entry_node_id="node-entry",
        nodes=[
            StoryNode("node-entry", "进入旧宅", "scene-entry", kind="entry"),
            StoryNode("node-cellar", "深入调查", "scene-cellar"),
            StoryNode("node-road", "驾车逃离", "scene-road", kind="ending"),
        ],
        edges=[
            StoryEdge("edge-cellar", "node-entry", "node-cellar", choice_label="打开地下室门"),
            StoryEdge("edge-road", "node-entry", "node-road", choice_label="立即驾车离开"),
        ],
    )
    runtime = ModuleRuntime(KeeperModule("分支模组", "branch.pdf", scenes, story=graph))
    with pytest.raises(ValueError, match="next_node_id"):
        runtime.advance("调查员做出了选择")
    result = runtime.advance("调查员打开地下室门", next_node_id="node-cellar")
    assert result["scene"] == "地下室"
    restored = ModuleRuntime.from_dict(runtime.to_dict())
    assert restored.current_node_id == "node-cellar"
    assert restored.history[-1]["edge"] == "edge-cellar"
