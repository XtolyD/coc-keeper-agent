# -*- coding: utf-8 -*-
import pytest

from coc_keeper.module.schema import ModuleDocument, Page
from coc_keeper.module.vision import VisionClient, VisionResult
from coc_keeper.module.extractor import (
    _guess_title, _merge_entities, _guess_summary, _as_list,
)


# ---- schema -----------------------------------------------------------------
def test_page_to_dict():
    p = Page(index=3, text="内容", image_path="p0003.png",
             visual={"content_type": "map"}, content_type="map")
    d = p.to_dict()
    assert d["index"] == 3
    assert d["content_type"] == "map"
    assert d["visual"]["content_type"] == "map"


def test_module_document_to_dict():
    m = ModuleDocument(source_pdf="a.pdf", title="黑水溪", pages=[Page(0, text="x")],
                       npcs=["A"], locations=["B"], extracted_at="2026-01-01T00:00:00")
    d = m.to_dict()
    assert d["source_pdf"] == "a.pdf"
    assert len(d["pages"]) == 1
    assert d["npcs"] == ["A"]


# ---- vision: 按需 thinking + max_tokens 配置 --------------------------------
def test_vision_uses_max_tokens_cap():
    # 关键：确保 max_tokens 是 API 上限，而非小值（防截断回归）
    assert hasattr(__import__("coc_keeper.module.vision", fromlist=["VisionClient"]), "MAX_TOKENS")
    from coc_keeper.module import vision
    assert vision.MAX_TOKENS > 100000


# ---- vision.__parse_json 容错 ----------------------------------------------
def test_parse_json_plain():
    assert VisionClient._parse_json('{"a":1}') == {"a": 1}


def test_parse_json_with_code_fence():
    raw = '```json\n{"content_type":"map","locations":["镇","森林"]}\n```'
    assert VisionClient._parse_json(raw)["content_type"] == "map"


def test_parse_json_leading_noise():
    # 模型偶尔输出前缀文字，应剥到第一个 { }
    raw = '好的，识别结果如下：{"name":"x"} 结束'
    assert VisionClient._parse_json(raw) == {"name": "x"}


def test_parse_json_invalid_falls_back():
    raw = "无法识别"
    d = VisionClient._parse_json(raw)
    assert d.get("content_type") == "text"
    assert d.get("description") == raw


# ---- VisionResult / _parse 分类 --------------------------------------------
def test_vision_parse_unknown_type_falls_to_text():
    vr = VisionClient._parse('{"content_type":"weird","description":"x"}')
    assert isinstance(vr, VisionResult)
    assert vr.content_type == "text"


def test_vision_parse_valid():
    vr = VisionClient._parse('{"content_type":"map","locations":["a"],"description":"d"}')
    assert vr.content_type == "map"
    assert vr.data == {"content_type": "map", "locations": ["a"], "description": "d"}


# ---- extractor 归并纯函数 ---------------------------------------------------
def _p(index, visual=None, text=""):
    return Page(index=index, text=text, visual=visual)


def test_guess_title_from_text_layer():
    pages = [_p(0, text=""), _p(1, text="黑水溪\n作者：xxx")]
    assert _guess_title(pages) == "黑水溪"


def test_guess_title_ignores_digits_and_short():
    pages = [_p(0, text="12"), _p(1, text="a")]
    assert _guess_title(pages) is None


def test_merge_entities_dedup_preserves_order():
    pages = [
        _p(0, visual={"locations": ["镇", "森林", "镇"]}),
        _p(1, visual={"monsters": ["食尸鬼"], "locations": ["洞穴"]}),
        _p(2, visual={"sanity_threats": ["看到怪"]}),
    ]
    npcs, locs, monsters, sanity = _merge_entities(pages)
    assert locs == ["镇", "森林", "洞穴"]  # 去重且保序
    assert monsters == ["食尸鬼"]
    assert sanity == ["看到怪"]


def test_guess_summary_first_description():
    pages = [_p(0, visual={"description": ""}),
             _p(1, visual={"description": "这是一段剧情"})]
    assert _guess_summary(pages) == "这是一段剧情"


def test_as_list_handles_none_str_list():
    assert _as_list(None) == []
    assert _as_list("a") == ["a"]
    assert _as_list(["a", "b"]) == ["a", "b"]
