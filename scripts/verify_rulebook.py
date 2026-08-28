# -*- coding: utf-8 -*-
"""规则书抽取完整性校验（离线一次性做，也可随时重跑）。

用途：在生成二次存储后，确认「清洗后文本」相对于「PDF 正文区原始文本」：
  1. 没有丢失任何【正文汉字】（页眉标题/页码/译者/引文署名除外）；
  2. 没有整页被误删；
  3. 只应删除噪声（章节标题、页码、译者署名、引文署名）。

判定思路：以「排除页眉/页码带后的正文区」为基准，逐页做汉字多重集差集。
凡是“正文区有、清洗后无”的汉字，都在核查范围内。缺失字若全部落入
【噪声字集合】（章节标题/译者/引文作者与作品名等），则判定通过；否则提示复核。

用法：
    python scripts/verify_rulebook.py            # 校验并输出缺失明细
    python scripts/verify_rulebook.py --strict   # 有任何非噪声缺失即退出码 1
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from coc_keeper.rulebook import read_page  # noqa: E402
from coc_keeper.rulebook import _CITATION_RE, _TRANSLATOR_RE  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebook"
PDF_PATH = DATA_DIR / "COC7th核心规则书v1.2.1.pdf"
TOP, FOOT = 0.06, 0.93


def _body_raw(page) -> str:
    """正文区原始文本（丢弃页眉/页码带）。"""
    H = page.rect.height
    parts = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        y0, y1 = b["bbox"][1], b["bbox"][3]
        if y1 < TOP * H or y0 > FOOT * H:
            continue
        parts.append("".join(s.get("text", "") for l in b.get("lines", []) for s in l.get("spans", [])))
    return "\n".join(parts)


def _han(s: str) -> Counter:
    return Counter(c for c in s if "\u4e00" <= c <= "\u9fff")


def _noise_han(page) -> Counter:
    """统计「应删噪声行」里的汉字：译者署名 + 引文署名。

    这些行由 _TRANSLATOR_RE/_CITATION_RE 识别，其内容本应被剔除，
    因此在完整性校验里不作为“正文丢失”计入。
    """
    H = page.rect.height
    c = Counter()
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        y0, y1 = b["bbox"][1], b["bbox"][3]
        if y1 < TOP * H or y0 > FOOT * H:
            continue
        txt = "".join(s.get("text", "") for l in b.get("lines", []) for s in l.get("spans", []))
        strip = txt.strip()
        if _TRANSLATOR_RE.match(strip) or _CITATION_RE.match(strip):
            c.update(ch for ch in txt if "\u4e00" <= ch <= "\u9fff")
    return c


def verify(doc) -> int:
    """校验全部页，返回是否通过（0 通过，1 有非噪声缺失）。

    判据：正文区汉字 - 清洗后汉字 - 应删噪声行(译者/引文署名)汉字。
    若余量为 0，说明清洗只删了噪声、未删正文；否则提示人工复核。
    """
    missing_pages: list[tuple[int, int, str, str]] = []
    for i in range(doc.page_count):
        page = doc[i]
        rc = _han(_body_raw(page))
        cc = _han("\n".join(read_page(page)))
        nc = _noise_han(page)
        miss = rc - cc - nc  # 剔除本应删除的噪声行
        total = sum(miss.values())
        if total <= 0:
            continue
        sample = "".join(miss.elements())[:24]
        missing_pages.append((i + 1, total, sample, "".join(miss.elements())[:32]))

    print(f"规则书: {doc.page_count} 页 | 剔除噪声行后仍有正文缺失的页 {len(missing_pages)} 页")
    for p, total, sample, _ in missing_pages:
        print(f"  p{p:3d} 缺失{total:4d}  {sample}")

    if missing_pages:
        print(f"\n结果：发现 {sum(m[1] for m in missing_pages)} 个可能属于正文的汉字丢失，"
              f"请人工核对（渲染对应页比对）。")
        return 1
    print("结果：所有缺失均为噪声（章节标题/页码/译者署名/引文署名），正文完整保留。")
    return 0


def main() -> None:
    ap = _argparse()
    args = ap.parse_args()
    if not PDF_PATH.exists():
        sys.exit(f"规则书不存在: {PDF_PATH}")
    doc = fitz.open(str(PDF_PATH))
    rc = verify(doc)
    doc.close()
    sys.exit(rc)


def _argparse():
    import argparse

    ap = argparse.ArgumentParser(description="规则书抽取完整性校验")
    return ap


if __name__ == "__main__":
    main()
