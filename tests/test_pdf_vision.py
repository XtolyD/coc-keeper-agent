# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pymupdf

from coc_keeper.pdf_vision import GrokPDFVisionExtractor


def build_pdf(path, pages):
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_grok_vision_extracts_pages_and_usage(tmp_path, monkeypatch):
    path = tmp_path / "vision.pdf"
    build_pdf(path, ["raw one", "raw two"])
    client = SimpleNamespace(settings=SimpleNamespace(model="grok-4.5"))
    extractor = GrokPDFVisionExtractor(client)

    monkeypatch.setattr(
        extractor,
        "_transcribe_page",
        lambda _page, number: (f"corrected page {number} with complete content", {"total_tokens": number}),
    )
    result = extractor.extract(path)
    assert result.pages == [
        "corrected page 1 with complete content",
        "corrected page 2 with complete content",
    ]
    assert result.usage["total_tokens"] == 3
    assert result.metadata()["status"] == "complete"


def test_grok_vision_falls_back_per_page(tmp_path, monkeypatch):
    path = tmp_path / "fallback.pdf"
    build_pdf(path, ["text layer remains available for this page"])
    client = SimpleNamespace(settings=SimpleNamespace(model="grok-4.5"))
    extractor = GrokPDFVisionExtractor(client)

    def fail(_page, _number):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(extractor, "_transcribe_page", fail)
    result = extractor.extract(path)
    assert "text layer remains available" in result.pages[0]
    assert result.metadata()["status"] == "partial"
    assert "第 1 页回退" in result.warnings[0]
