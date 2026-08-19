# -*- coding: utf-8 -*-
import pymupdf
import pytest

from coc_keeper.modules import (
    KeeperModule, ModuleActor, ModuleEvent, ModuleLocation, ModuleRuntime,
    ModuleSection, PDFModuleImporter, StoryEdge, StoryGraph, StoryNode,
)
from coc_keeper.module_store import ModuleStore


def build_pdf(path, pages, toc=None):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    if toc:
        doc.set_toc(toc)
    doc.save(path)
    doc.close()


def test_pdf_module_import_short_and_long(tmp_path):
    path = tmp_path / "scenario.pdf"
    build_pdf(path, ["Opening room with a locked door and clue A.", "Second room contains clue B and an exit."])
    module = PDFModuleImporter(max_pages_per_section=1).import_pdf(path)
    assert module.title.startswith("Opening room")
    assert len(module.sections) == 2
    assert module.sections[0].page_start == 1
    assert module.sections[1].page_end == 2


def test_pdf_toc_controls_sections(tmp_path):
    path = tmp_path / "toc.pdf"
    build_pdf(path, ["Intro text here.", "Investigation text here.", "Final text here."], [[1, "Intro", 1], [1, "Finale", 3]])
    module = PDFModuleImporter(max_pages_per_section=8).import_pdf(path)
    assert [section.keeper_title for section in module.sections] == ["Intro", "Finale"]
    assert module.sections[0].page_end == 2


def test_hybrid_pdf_import_preserves_raw_and_corrected_text(tmp_path):
    path = tmp_path / "hybrid.pdf"
    build_pdf(path, ["Raw column order text."])
    module = PDFModuleImporter().import_pdf(
        path,
        page_text_override=["Correct visual reading order."],
        extraction_metadata={"model": "grok-4.5", "status": "complete"},
    )
    chunk = module.source_chunks[0]
    assert chunk.text.endswith("Correct visual reading order.")
    assert chunk.raw_text.endswith("Raw column order text.")
    assert chunk.extraction_method == "hybrid-vision"
    assert "【视觉校正文】" in chunk.analysis_text()
    assert "【PDF 文本层原文】" in chunk.analysis_text()
    assert module.analysis["vision"]["model"] == "grok-4.5"


def make_runtime():
    return ModuleRuntime(KeeperModule("测试模组", "test.pdf", [
        ModuleSection("scene-001", "门厅", "场景 1", 1, 1, "门厅里有一把生锈钥匙。", objectives=["找到钥匙"]),
        ModuleSection(
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


def test_scanned_pdf_is_preserved_for_later_vision_analysis(tmp_path):
    path = tmp_path / "scan.pdf"
    build_pdf(path, [""])
    module = PDFModuleImporter().import_pdf(path)
    assert module.analysis["status"] == "needs-vision"
    assert "等待 Grok 视觉校正" in module.source_chunks[0].text


def test_module_store_can_update_and_delete(tmp_path):
    store = ModuleStore(tmp_path / "modules")
    record = store.add(make_runtime().module)
    updated = KeeperModule("修订模组", "revised.pdf", [
        ModuleSection("scene-new", "修订场景", "当前地点", 3, 4, "修订后的 Keeper 原文。"),
    ])
    store.save(record.id, updated)
    assert store.get(record.id).module.title == "修订模组"
    store.delete(record.id)
    assert store.list() == []


def test_module_store_preserves_and_deletes_source_pdf(tmp_path):
    path = tmp_path / "source.pdf"
    build_pdf(path, ["Source PDF must remain available for later vision analysis."])
    store = ModuleStore(tmp_path / "modules")
    record = store.import_pdf(path)
    stored_pdf = store.source_pdf_path(record.id)
    assert stored_pdf is not None
    assert stored_pdf.read_bytes() == path.read_bytes()
    store.delete(record.id)
    assert not stored_pdf.exists()


def test_v1_sections_migrate_to_structured_v2():
    module = KeeperModule.from_dict({
        "version": 1, "title": "旧模组", "source_name": "legacy.pdf",
        "sections": [{
            "id": "scene-old", "keeper_title": "旧门厅", "public_title": "门厅",
            "page_start": 2, "page_end": 3, "text": "门厅里藏着一把钥匙。",
            "objectives": ["找到钥匙"], "secrets": ["钥匙属于医生"],
        }],
    })
    payload = module.to_dict()
    assert payload["version"] == 2
    assert "sections" not in payload
    assert payload["source_chunks"][0]["text"] == "门厅里藏着一把钥匙。"
    assert payload["scenes"][0]["source_chunk_ids"] == ["source-001"]
    assert payload["story"]["entry_node_id"] == "node-001"
    assert payload["analysis"]["migration"] == "v1-sections-to-v2"


def test_importer_extracts_each_actor_stat_block(tmp_path):
    path = tmp_path / "actors.pdf"
    build_pdf(path, [
        "Characters and creatures\nMia,\nInvestigator ally\n"
        "STR 40 CON 50 SIZ 45 DEX 70 INT 80\n"
        "APP 60 POW 50 EDU 85 SAN 50 HP 9\n"
        "Skills\nSpotHidden55%, Stealth40%",
    ])
    module = PDFModuleImporter().import_pdf(path)
    assert len(module.actors) == 1
    actor = module.actors[0]
    assert actor.name == "Mia"
    assert actor.attributes["DEX"] == 70
    assert actor.attributes["HP"] == 9
    assert actor.skills["SpotHidden"] == 55


def test_importer_merges_stream_and_visual_actor_extraction():
    first = ModuleActor("actor-old", "Mia", attributes={"HP": 9}, source_pages=[1])
    corrected = ModuleActor("actor-new", "Mia", attributes={"DEX": 70}, skills={"潜行": 40}, source_pages=[2])
    monster = ModuleActor("actor-monster", "Dead Light", kind="monster", armor="6", source_pages=[3])
    actors = PDFModuleImporter._merge_local_actors([[first], [corrected, monster]])
    assert [actor.id for actor in actors] == ["actor-001", "actor-002"]
    assert actors[0].attributes == {"DEX": 70, "HP": 9}
    assert actors[0].skills["潜行"] == 40
    assert actors[0].source_pages == [1, 2]


def test_local_analysis_stores_nonstandard_monster_combat_block():
    actors = PDFModuleImporter._extract_stat_blocks([
        "Dead Light,\n潜藏的吞噬者\n攻击方式\n"
        "卷须抽打 70%（35/14），伤害1D6+2\n"
        "护甲：6 点护甲\n理智损失：目睹时 1/1D4",
    ])
    assert len(actors) == 1
    monster = actors[0]
    assert monster.kind == "monster"
    assert monster.attacks[0]["value"] == 70
    assert monster.armor == "6 点护甲"
    assert monster.sanity_loss == "目睹时 1/1D4"


def test_structured_context_resolves_current_scene_entities():
    actor = ModuleActor("actor-doctor", "韦伯医生", role="线索提供者", attributes={"HP": 8})
    location = ModuleLocation("location-study", "医生书房", features=["上锁的抽屉"])
    scene = ModuleSection(
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
        ModuleSection("scene-entry", "入口", "入口", 1, 1, "入口。"),
        ModuleSection("scene-cellar", "地下室", "地下室", 2, 2, "地下室。"),
        ModuleSection("scene-road", "公路", "公路", 3, 3, "公路。"),
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
