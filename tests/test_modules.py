# -*- coding: utf-8 -*-
import pymupdf
import pytest

from coc_keeper.modules import (
    KeeperModule, ModuleRuntime, ModuleSection, PDFModuleImporter,
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


def test_scanned_pdf_requires_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    build_pdf(path, [""])
    with pytest.raises(ValueError, match="OCR"):
        PDFModuleImporter().import_pdf(path)


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
