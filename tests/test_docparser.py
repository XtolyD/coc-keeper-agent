# -*- coding: utf-8 -*-
import io
import json
import zipfile
from pathlib import Path

import pytest

from coc_keeper.docparser.result import (
    Block, ParseResult, parse_content_list, is_done_state, is_failed_state,
)
from coc_keeper.docparser.client import MinerUClient, DocParserError


# ---- result：content_list 纯函数解析 ----------------------------------------
def test_parse_content_list_basic():
    data = [
        {"type": "text", "text": "第三卷", "text_level": "2", "bbox": [1, 2, 3, 4], "page_idx": "0"},
        {"type": "text", "text": "正文内容", "text_level": "", "bbox": [1, 2, 3, 4], "page_idx": "1"},
        {"type": "image", "text": "", "bbox": [1, 2, 3, 4], "page_idx": "1"},
    ]
    blocks = parse_content_list(data)
    assert len(blocks) == 3
    assert blocks[0].type == "text" and blocks[0].is_title
    assert blocks[0].page_idx == 0
    assert blocks[1].text == "正文内容" and not blocks[1].is_title
    assert blocks[2].type == "image" and blocks[2].text == ""


def test_parse_content_list_tolerates_missing_and_bad_fields():
    data = [
        {},  # 跳过
        {"type": "table", "text_level": None, "bbox": "bad", "page_idx": ""},
        {"type": "text", "text": "a", "bbox": [1, 2, 3, 4], "page_idx": "x"},
    ]
    blocks = parse_content_list(data)
    # {} 被跳过，剩余两个
    assert len(blocks) == 2
    assert blocks[0].type == "table" and blocks[0].bbox == []
    assert blocks[1].page_idx == 0  # 非法 page_idx → 默认 0


def test_parse_content_list_preserves_order():
    data = [
        {"type": "text", "text": "第3页", "page_idx": "3"},
        {"type": "text", "text": "第2页", "page_idx": "2"},
    ]
    blocks = parse_content_list(data)
    assert [b.page_idx for b in blocks] == [3, 2]  # 保持输入顺序


# ---- result：状态判断 -------------------------------------------------------
def test_is_done_and_failed_state():
    assert is_done_state("done")
    assert not is_done_state("running")
    assert is_failed_state("failed")
    assert not is_failed_state("done")


# ---- Block / ParseResult 序列化 --------------------------------------------
def test_block_and_result_to_dict():
    b = Block(type="text", text="x", text_level="2", page_idx=0, bbox=[1, 2, 3, 4])
    r = ParseResult(source_pdf="a.pdf", blocks=[b], markdown="# t", images_dir="img")
    d = r.to_dict()
    assert d["blocks"][0]["text"] == "x"
    assert d["markdown"] == "# t"
    assert d["images_dir"] == "img"


# ---- client：调用链（mock session）------------------------------------------
class _FakeZip:
    """模拟 MinerU 结果 zip。"""
    def __init__(self, content_list, markdown):
        self.buf = io.BytesIO()
        with zipfile.ZipFile(self.buf, "w") as z:
            z.writestr("abc_content_list.json", content_list)
            z.writestr("full.md", markdown)

    def bytes(self):
        return self.buf.getvalue()


class _FakeSession:
    """模拟 requests.Session：记录调用，返回预设响应。"""
    def __init__(self, upload_status=200, poll_states=("running", "done"), zip_url="https://z/x.zip"):
        self.calls = {"post": [], "get": [], "put": []}
        self.upload_status = upload_status
        self.poll_states = list(poll_states)
        self.zip_url = zip_url
        self._zip = None  # 由测试设置

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls["post"].append((url, json))
        return _Resp(200, {
            "code": 0,
            "data": {"batch_id": "B1", "file_urls": ["https://oss/up.pdf"]},
        })

    def put(self, url, data=None, timeout=None):
        self.calls["put"].append((url,))
        return _Resp(self.upload_status, {})

    def get(self, url, headers=None, timeout=None):
        self.calls["get"].append((url,))
        if url.endswith(".zip") or url == self.zip_url:
            return _Resp(200, None)  # 二进制：返回原始 content
        # 轮询接口
        state = self.poll_states.pop(0) if self.poll_states else "done"
        return _Resp(200, {"code": 0, "data": {"batch_id": "B1",
            "extract_result": [{"file_name": "a.pdf", "state": state,
                                "err_msg": "", "full_zip_url": self.zip_url}]}})


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.content = b""
        if data is not None:
            import json as _json
            self.content = _json.dumps(data, ensure_ascii=False).encode()

    def json(self):
        import json as _json
        return _json.loads(self.content.decode())


def test_client_parse_pdf_end_to_end(tmp_path):
    zip_data = _FakeZip(
        content_list='[{"type":"text","text":"标题","text_level":"2","bbox":[1,2,3,4],"page_idx":"0"}]',
        markdown="# 标题\n正文",
    )
    sess = _FakeSession()
    # 重写 get：记录调用；zip 返回二进制，轮询返回序列状态
    def patched_get(url, headers=None, timeout=None):
        sess.calls["get"].append((url,))
        if url.endswith(".zip"):
            r = _Resp(200, None)
            r.content = zip_data.bytes()
            return r
        state = sess.poll_states.pop(0) if sess.poll_states else "done"
        return _Resp(200, {"code": 0, "data": {"batch_id": "B1",
            "extract_result": [{"file_name": "a.pdf", "state": state,
                                "err_msg": "", "full_zip_url": "https://z/x.zip"}]}})
    sess.get = patched_get

    client = MinerUClient(api_key="sk-test", base_url="https://mineru.net", session=sess, poll_interval=0)
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    out_dir = str(tmp_path / "out")
    result = client.parse_pdf(str(pdf), out_dir=out_dir)

    # 调用链：post /file-urls/batch → put 上传 → get 轮询 → get zip
    assert any("file-urls/batch" in u for u, _ in sess.calls["post"])
    assert sess.calls["put"]  # 上传了文件
    assert any("extract-results/batch" in u for (u,) in sess.calls["get"])

    assert result.blocks and result.blocks[0].text == "标题"
    assert result.markdown == "# 标题\n正文"
    assert result.images_dir == str(Path(out_dir) / "images")
    assert result.content_list_path  # 原始 content_list.json 已落盘


def test_client_parse_pdf_failed_state_raises(tmp_path):
    sess = _FakeSession(poll_states=("failed",))
    def patched_get(url, headers=None, timeout=None):
        return _FakeSession.get(sess, url, headers, timeout)
    sess.get = patched_get
    sess._zip = b""
    client = MinerUClient(api_key="sk-test", base_url="https://mineru.net", session=sess, poll_interval=0)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF fake")
    with pytest.raises(DocParserError):
        client.parse_pdf(str(pdf))


def test_client_normalizes_base_url():
    client = MinerUClient(api_key="k", base_url="https://mineru.net/")
    assert client.base_url == "https://mineru.net"
