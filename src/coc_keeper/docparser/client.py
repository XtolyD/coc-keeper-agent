# -*- coding: utf-8 -*-
"""MinerU 文档解析客户端。

API 流程（见 docs/docparser-spec.md §1）：
1. POST /api/v4/file-urls/batch    申请上传链接 → batch_id + file_urls[]
2. PUT  {file_urls[i]}             上传本地文件
3. GET  /api/v4/extract-results/batch/{batch_id}   轮询 → state + full_zip_url
4. 下载 zip → ParseResult（content_list + full.md + images）

设计（便于单测）：
- 通过可注入的 `_session`（requests.Session 或 mock）做 HTTP，便于测试不联网。
- api_key 来自 config；base_url 可注入；绝不打印密钥。
- 幂等：每次 parse_pdf 独立申请 batch；同 PDF 可重复调用。
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from ..config import Settings
from .result import ParseResult, parse_content_list


class DocParserError(RuntimeError):
    """MinerU 解析失败（网络/状态/超时）。"""


#: 默认轮询间隔与总超时
POLL_INTERVAL = 8.0
POLL_TIMEOUT = 300.0


class MinerUClient:
    """基于 requests 的 MinerU 客户端。可注入 session / base_url 便于测试。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[object] = None,
        poll_interval: float = POLL_INTERVAL,
        timeout: float = POLL_TIMEOUT,
    ):
        s = Settings()
        self.api_key = api_key if api_key is not None else s.mineru_api_key
        self.base_url = (base_url or s.mineru_base_url or "https://mineru.net").rstrip("/")
        self.session = session
        self._own_session = session is None
        self.poll_interval = poll_interval
        self.timeout = timeout

    def _get_session(self):
        if self._own_session and self.session is None:
            self.session = requests.Session()
        return self.session

    def _headers(self, content_type: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if content_type:
            h["Content-Type"] = "application/json"
        return h

    # ---- 对外接口 -------------------------------------------------------------
    def parse_pdf(
        self,
        pdf_path: str,
        *,
        model_version: str = "vlm",
        enable_formula: bool = False,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: Optional[str] = None,
        out_dir: Optional[str] = None,
    ) -> ParseResult:
        """解析一个 PDF，返回 ParseResult。

        Args:
            pdf_path: 本地 PDF 路径。
            page_ranges: 页码范围（如 "2,4-6"），None 则整本。
        """
        pdf_path = str(pdf_path)
        if not Path(pdf_path).exists():
            raise DocParserError(f"文件不存在: {pdf_path}")

        # 1. 申请上传链接
        batch_id, file_urls = self._request_upload_urls(pdf_path, model_version,
                                                        enable_formula, enable_table, language,
                                                        page_ranges)
        # 2. 上传
        self._upload_file(file_urls[0], pdf_path)
        # 3. 轮询
        extract = self._poll_batch(batch_id)
        full_zip_url = extract.get("full_zip_url", "")
        if not full_zip_url:
            raise DocParserError(f"解析完成但无结果 zip: state={extract.get('state')}")
        # 4. 下载解压 → ParseResult
        return self._download_result(full_zip_url, pdf_path, out_dir)

    # ---- 内部：各步 ------------------------------------------------------------
    def _request_upload_urls(
        self, pdf_path: str, model_version: str,
        enable_formula: bool, enable_table: bool, language: str,
        page_ranges: Optional[str] = None,
    ) -> tuple[str, list[str]]:
        """POST /file-urls/batch → (batch_id, [file_url])。"""
        files = {"name": Path(pdf_path).name}
        if page_ranges:
            files["page_ranges"] = page_ranges
        body = {
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language,
            "files": [files],
        }
        resp = self._post("/api/v4/file-urls/batch", body)
        data = resp.get("data") or {}
        batch_id = data.get("batch_id", "")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise DocParserError(f"申请上传链接失败: {resp}")
        return batch_id, file_urls

    def _upload_file(self, file_url: str, pdf_path: str) -> None:
        """PUT 本地文件到 OSS 签名链接。"""
        session = self._get_session()
        with open(pdf_path, "rb") as f:
            r = session.put(file_url, data=f, timeout=600)
        if r.status_code >= 300:
            raise DocParserError(f"上传失败: HTTP {r.status_code}")

    def _poll_batch(self, batch_id: str) -> dict:
        """GET /extract-results/batch/{id}，轮询到 done/failed。"""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            resp = self._get(f"/api/v4/extract-results/batch/{batch_id}")
            extract_list = (resp.get("data") or {}).get("extract_result") or []
            item = extract_list[0] if extract_list else {}
            state = item.get("state", "")
            if state == "done":
                return item
            if state == "failed":
                raise DocParserError(f"解析失败: {item.get('err_msg')}")
            time.sleep(self.poll_interval)
        raise DocParserError("轮询超时")

    def _download_result(self, full_zip_url: str, pdf_path: str, out_dir: Optional[str]) -> ParseResult:
        """下载 zip → 完整解压到 out_dir，解析出 content_list/full.md/images → ParseResult。

        zip 整体落盘（保留 content_list.json / full.md / images/），便于下游 vision 关联图片。
        """
        session = self._get_session()
        r = session.get(full_zip_url, timeout=600)
        if r.status_code >= 300:
            raise DocParserError(f"下载结果失败: HTTP {r.status_code}")
        zip_bytes = r.content

        import tempfile
        tmp_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="mineru_"))
        tmp_dir.mkdir(parents=True, exist_ok=True)

        markdown = ""
        blocks = []
        content_list_path = ""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                base = Path(name).name
                if name.endswith("_content_list.json") and "v2" not in name:
                    raw = zf.read(name)
                    (tmp_dir / base).write_bytes(raw)
                    content_list_path = str(tmp_dir / base)
                    try:
                        blocks = parse_content_list(json.loads(raw.decode("utf-8")))
                    except (ValueError, TypeError):
                        pass
                elif base == "full.md":
                    markdown = zf.read(name).decode("utf-8")
                    (tmp_dir / base).write_bytes(markdown.encode("utf-8"))
                elif "/images/" in name or name.startswith("images/"):
                    p = tmp_dir / "images" / Path(name).name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(zf.read(name))

        if not blocks and not markdown:
            raise DocParserError("结果 zip 无 content_list / full.md")

        return ParseResult(
            source_pdf=str(pdf_path),
            blocks=blocks,
            markdown=markdown,
            images_dir=str(tmp_dir / "images"),
            content_list_path=content_list_path,
            parsed_at=datetime.now().isoformat(timespec="seconds"),
        )

    # ---- HTTP 封装（便于 mock）------------------------------------------------
    def _post(self, path: str, body: dict) -> dict:
        session = self._get_session()
        r = session.post(self.base_url + path, headers=self._headers(True), json=body, timeout=60)
        return self._json_or_raise(r)

    def _get(self, path: str) -> dict:
        session = self._get_session()
        r = session.get(self.base_url + path, headers=self._headers(), timeout=60)
        return self._json_or_raise(r)

    @staticmethod
    def _json_or_raise(r) -> dict:
        try:
            data = r.json()
        except ValueError as e:
            raise DocParserError(f"非 JSON 响应 (HTTP {r.status_code})") from e
        if r.status_code >= 300 or data.get("code") not in (0, None):
            raise DocParserError(f"API 错误 (HTTP {r.status_code}): {data.get('msg', r.text[:120])}")
        return data
