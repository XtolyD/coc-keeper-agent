# -*- coding: utf-8 -*-
import pytest

from coc_keeper.vision import VisionClient, VisionResult, MAX_TOKENS
from coc_keeper.module.extractor import ModuleExtractor
from coc_keeper.module.schema import ModuleDocument
from coc_keeper.docparser.result import Block, ParseResult


# ---- vision: max_tokens 配置 -----------------------------------------------
def test_vision_max_tokens_is_api_cap():
    # 关键：max_tokens 是 API 上限（防截断回归），而非小值
    assert MAX_TOKENS == 393216
    assert MAX_TOKENS > 100000


# ---- vision._parse_json 容错 -----------------------------------------------
def test_parse_json_plain():
    assert VisionClient._parse_json('{"a":1}') == {"a": 1}


def test_parse_json_with_code_fence():
    raw = '```json\n{"content_type":"map","locations":["镇","森林"]}\n```'
    assert VisionClient._parse_json(raw)["content_type"] == "map"


def test_parse_json_leading_noise():
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


# ---- module: extract_from_result（mock vision，不联网）----------------------

class _FakeVision:
    """模拟 VisionClient：按 image 内容返回预设分类。"""
    def __init__(self, page_type="illustration"):
        self.calls = []
        self.page_type = page_type

    def recognize_page(self, img, *a, **k):
        self.calls.append(("page", img))
        return VisionResult(content_type=self.page_type, data={"content_type": self.page_type})

    def recognize_map(self, img, *a, **k):
        self.calls.append(("map", img))
        return {"locations": ["黑水溪镇", "黑溪森林", "洞穴"]}

    def recognize_character(self, img, *a, **k):
        self.calls.append(("character", img))
        return {"name": "莱布·瓦伦汀", "attributes": {"STR": 75}}


def test_extract_from_result_with_map_image(tmp_path):
    # 构造一个带 image 块的 ParseResult
    img = tmp_path / "images" / "map.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"fake")

    result = ParseResult(
        source_pdf="mod.pdf",
        markdown="",
        images_dir=str(tmp_path / "images"),
        blocks=[
            Block(type="text", text="黑水溪 模组", text_level="1", page_idx=0),
            Block(type="image", text="", text_level="", page_idx=0, img_path="images/map.jpg"),
            Block(type="text", text="调查员前往黑水溪镇调查", text_level="", page_idx=1),
        ],
    )
    fv = _FakeVision(page_type="map")
    doc = ModuleExtractor(vision=fv).extract_from_result(result)

    assert isinstance(doc, ModuleDocument)
    # 图片被视觉识别为 map，抽取地名
    assert doc.locations == ["黑水溪镇", "黑溪森林", "洞穴"]
    assert doc.image_results and doc.image_results[0]["content_type"] == "map"
    assert doc.text_count == 2
    # 标题猜取
    assert doc.title == "黑水溪 模组"


def test_extract_from_result_text_only_no_vision():
    # 无 image 块：不触发视觉，纯文本归并
    result = ParseResult(
        source_pdf="m.pdf",
        blocks=[Block(type="text", text="模组内容", text_level="", page_idx=0)],
    )
    fv = _FakeVision()
    doc = ModuleExtractor(vision=fv).extract_from_result(result)
    assert fv.calls == []          # 不应调用视觉
    assert doc.image_results == []
    assert doc.text_count == 1
