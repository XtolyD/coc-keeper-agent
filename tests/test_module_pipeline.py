# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from coc_keeper.docparser.result import Block, ParseResult
from coc_keeper.module_pipeline.assembler import ModuleAssembler
from coc_keeper.module_pipeline.ingest import build_source_chunks
from coc_keeper.module_pipeline.mineru_parser import CachedMinerUDocumentParser
from coc_keeper.module_pipeline.pipeline import ModuleImportPipeline, ModuleImportRequest
from coc_keeper.module_pipeline.review import LLMModuleReviewer
from coc_keeper.module_pipeline.ports import ReviewOutcome
from coc_keeper.modules import ModuleSourceChunk


def _parsed(**kwargs) -> ParseResult:
    return ParseResult(
        source_pdf=str(kwargs.pop("source_pdf", "scenario.pdf")),
        blocks=kwargs.pop("blocks", [
            Block("text", "第一章", "1", 0),
            Block("text", "门厅里有一把钥匙。", "", 0),
            Block("text", "地下室有怪物。", "", 1),
        ]),
        markdown=kwargs.pop("markdown", ""),
        images_dir=str(kwargs.pop("images_dir", "")),
        content_list_path="",
        parsed_at="2026-01-01T00:00:00",
    )


def test_ingest_splits_by_heading_and_page_limit():
    parsed = _parsed(blocks=[
        Block("text", "第一章", "1", 0),
        Block("text", "第一段。", "", 0),
        Block("text", "第二段。", "", 1),
        Block("text", "第二章", "1", 2),
        Block("text", "第三段。", "", 2),
        Block("table", "", "", 2, table_body="|STR|CON|\n|40|50|"),
        Block("header", "页眉", "", 2),
    ])
    chunks = build_source_chunks(parsed, max_pages_per_section=1)
    assert [chunk.heading for chunk in chunks] == ["第一章", "第一章", "第二章"]
    assert chunks[0].page_start == 1 and chunks[0].page_end == 1
    assert chunks[1].page_start == 2
    assert "|STR|CON|" in chunks[2].text
    assert all(chunk.extraction_method == "mineru" for chunk in chunks)


def test_assembler_builds_v2_module_with_traceable_chunks():
    parsed = _parsed()
    chunks = build_source_chunks(parsed)
    module = ModuleAssembler().build(parsed, chunks, title="测试模组")
    assert module.title == "测试模组"
    assert len(module.scenes) == len(chunks)
    assert module.source_chunks[0].raw_text == module.source_chunks[0].text
    assert module.analysis["mode"] == "mineru"
    assert module.analysis["status"] == "needs-review"
    assert module.story.entry_node_id == "node-001"


class _FakeVision:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.calls = 0

    def review_chunks(self, prompt, image_paths):
        self.calls += 1
        if self.error:
            raise self.error
        return self.payload


def test_reviewer_returns_corrected_text_and_raw_text():
    parsed = _parsed()
    chunks = build_source_chunks(parsed)
    vision = _FakeVision({"chunks": [
        {"id": chunks[0].id, "text": "复核后的门厅。", "issues": ["修正双栏"], "confidence": "high"},
    ], "images": [{"page": 1, "type": "map", "locations": ["门厅"], "description": "地图"}]})
    outcome = LLMModuleReviewer(vision, batch_chars=100_000).review(chunks, parsed)
    corrected = outcome.chunks[0]
    assert corrected.text == "复核后的门厅。"
    assert corrected.raw_text == chunks[0].text
    assert corrected.extraction_method == "mineru+deepseek"
    assert corrected.review["issues"] == ["修正双栏"]
    assert outcome.visual_entities[0]["locations"] == ["门厅"]
    assert outcome.status == "complete"


def test_reviewer_falls_back_per_batch_without_losing_chunks():
    parsed = _parsed()
    chunks = build_source_chunks(parsed)
    outcome = LLMModuleReviewer(_FakeVision(error=RuntimeError("network"))).review(chunks, parsed)
    assert [chunk.id for chunk in outcome.chunks] == [chunk.id for chunk in chunks]
    assert all(chunk.extraction_method == "mineru" for chunk in outcome.chunks)
    assert outcome.status == "partial"
    assert "network" in outcome.warnings[0]


class _FakeParser:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = 0

    def parse(self, pdf_path, *, refresh=False):
        self.calls += 1
        return self.parsed


class _FakeAnalyzer:
    def __init__(self):
        self.called = False

    def analyze(self, module):
        self.called = True
        module.analysis = {**module.analysis, "mode": "llm", "status": "complete"}
        return module


def test_pipeline_orders_parse_review_assemble_and_analyze():
    parsed = _parsed()
    stages = []
    analyzer = _FakeAnalyzer()
    pipeline = ModuleImportPipeline(
        parser=_FakeParser(parsed),
        reviewer=LLMModuleReviewer(_FakeVision({"chunks": []})),
        analyzer=analyzer,
    )
    module = pipeline.run(
        ModuleImportRequest(Path("scenario.pdf"), title="流水线模组"),
        progress=stages.append,
    )
    assert analyzer.called is True
    assert module.analysis["status"] == "complete"
    assert stages[0] == "MinerU 解析 PDF"
    assert stages[-1] == "完成"


class _FakeMinerU:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = 0

    def parse_pdf(self, pdf_path, *, out_dir=None):
        self.calls += 1
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "scenario_content_list.json").write_text(
            '[{"type":"text","text":"缓存正文","text_level":"","page_idx":"0"}]',
            encoding="utf-8",
        )
        (out / "full.md").write_text("# 缓存正文", encoding="utf-8")
        return self.parsed


def test_cached_parser_reuses_mineru_result(tmp_path):
    pdf = tmp_path / "scenario.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    client = _FakeMinerU(_parsed())
    parser = CachedMinerUDocumentParser(client, tmp_path / "cache")
    first = parser.parse(pdf)
    second = parser.parse(pdf)
    assert client.calls == 1
    assert first.blocks[0].text == "第一章"
    assert second.blocks[0].text == "缓存正文"


def test_ingest_keeps_image_only_page_as_chunk():
    parsed = _parsed(blocks=[
        Block("image", "", "", 0, img_path="images/map.jpg"),
        Block("text", "第二章", "1", 1),
        Block("text", "正文。", "", 1),
    ])
    chunks = build_source_chunks(parsed)
    assert chunks[0].image_paths == ["images/map.jpg"]
    assert chunks[0].page_start == 1
    assert chunks[0].heading == "图片页 1"


def test_ingest_does_not_attach_late_image_to_previous_page_chunk():
    parsed = _parsed(blocks=[
        Block("text", "第一章", "1", 0),
        Block("text", "第一页正文。", "", 0),
        Block("image", "", "", 2, img_path="images/late.jpg"),
    ])
    chunks = build_source_chunks(parsed, max_pages_per_section=1)
    assert len(chunks) == 2
    assert chunks[0].page_end == 1
    assert chunks[1].page_start == 3
    assert chunks[1].image_paths == ["images/late.jpg"]


def test_assembler_tolerates_malformed_visual_entities():
    parsed = _parsed()
    chunks = build_source_chunks(parsed)
    review = ReviewOutcome(chunks=chunks, visual_entities=[
        {"type": "character", "name": "医生", "attributes": "not-a-dict", "page": "封面"},
        {"type": "map", "locations": "not-a-list", "page": 2},
    ])
    module = ModuleAssembler().build(parsed, chunks, review, title="容错模组")
    assert module.title == "容错模组"
    assert any(actor.name == "医生" for actor in module.actors)
    assert module.analysis["visual_entities"]
