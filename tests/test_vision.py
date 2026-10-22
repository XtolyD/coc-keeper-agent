# -*- coding: utf-8 -*-
from types import SimpleNamespace

from coc_keeper.vision import VisionClient, VisionResult, MAX_TOKENS


def test_vision_max_tokens_is_api_cap():
    assert MAX_TOKENS == 393216
    assert MAX_TOKENS > 100000


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


def test_vision_parse_unknown_type_falls_to_text():
    vr = VisionClient._parse('{"content_type":"weird","description":"x"}')
    assert isinstance(vr, VisionResult)
    assert vr.content_type == "text"


def test_vision_parse_valid():
    vr = VisionClient._parse('{"content_type":"map","locations":["a"],"description":"d"}')
    assert vr.content_type == "map"
    assert vr.data == {"content_type": "map", "locations": ["a"], "description": "d"}


class _FakeChatClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.payload))],
        )


def test_review_chunks_sends_text_and_images(tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"fake-image")
    fake = _FakeChatClient('{"chunks":[{"id":"source-001","text":"复核正文"}]}')
    vision = VisionClient(client=fake)
    payload = vision.review_chunks("请复核", [str(image)])
    assert payload["chunks"][0]["text"] == "复核正文"
    content = fake.requests[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "请复核"}
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert fake.requests[0]["response_format"] == {"type": "json_object"}
