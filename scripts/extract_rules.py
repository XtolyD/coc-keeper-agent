# -*- coding: utf-8 -*-
"""规则书处理：把 CoC 7th 规则书 PDF 整理成「清洗 + 分栏排序 + 按 TOC 分层」的二次存储。

有别于旧 `extract_rules.py`（只导出全文到 fulltext.txt，检索时再跳转查找），
本脚本产出**可检索、可回溯页号**的干净语料：

- `data/rulebook/rules_structure.json`：按 TOC 分层（章/节/小节）+ 每节点的页区间、
  标题、清洗后的正文。这是 RAG 的主索引，`search_rules` 直接按此命中并引用页号。
- `data/rulebook/rules_pages/*.txt`：每页一份的清洗后文本（页号即文件名），
  便于 BM25 按页切块检索。

清洗规则（见 src/coc_keeper/rulebook.py）：
- 双栏按「左列全部→右列全部」重排；
- 去掉页眉带、页码带、译者署名、引用署名、空白/纯图块。

用法：
    python scripts/extract_rules.py --build      # 重新生成二次存储
    python scripts/extract_rules.py --pages 24   # 打印某页清洗后文本
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz  # pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from coc_keeper.rulebook import build_structure, extract_pages  # noqa: E402

# 统一 UTF-8 输出，避免 Windows 控制台 GBK 编码问题
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PDF_PATH = Path(r"C:\Users\XtolyD\Desktop\COC7th核心规则书v1.2.1.pdf")
# 优先取 data/rulebook 下已存在的同名源文件，方便在项目内直接跑
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebook"
OUT_STRUCTURE = DATA_DIR / "rules_structure.json"
OUT_PAGES_DIR = DATA_DIR / "rules_pages"


def open_doc() -> fitz.Document:
    path = PDF_PATH if PDF_PATH.exists() else DATA_DIR / "COC7th核心规则书v1.2.1.pdf"
    if not path.exists():
        sys.exit(f"规则书不存在: {path}")
    return fitz.open(str(path))


def dump_structure(doc: fitz.Document) -> None:
    """生成规则书的分级结构 JSON（RAG 主索引）。"""
    pages = extract_pages(doc)
    sections = build_structure(doc)

    def section_dict(s) -> dict:
        return {
            "level": s.level,
            "title": s.title,
            "page_range": [s.start_page, s.end_page],
            "text": "\n".join(
                line for p in range(s.start_page, s.end_page + 1) for line in pages.get(p, [])
            ).strip(),
            "children": [section_dict(c) for c in s.children],
        }

    tree = [section_dict(s) for s in sections]
    OUT_STRUCTURE.parent.mkdir(parents=True, exist_ok=True)
    OUT_STRUCTURE.write_text(
        json.dumps({"source": len(doc), "title": "克苏鲁的呼唤 第七版 核心规则书",
                    "sections": tree}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] 结构索引 -> {OUT_STRUCTURE}（{len(doc)} 页 / {len(pages)} 页清洗成功）")


def dump_pages(doc: fitz.Document) -> None:
    """每页一份清洗后文本，用于 BM25 按页切块。"""
    pages = extract_pages(doc)
    OUT_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for p, lines in sorted(pages.items()):
        (OUT_PAGES_DIR / f"p{p:04d}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 分页语料 -> {OUT_PAGES_DIR}/（{len(pages)} 页）")


def print_pages(doc: fitz.Document, numbers: list[int]) -> None:
    from coc_keeper.rulebook import read_page

    for n in numbers:
        idx = n - 1
        if idx < 0 or idx >= doc.page_count:
            print(f"页码越界: {n}")
            continue
        print(f"\n===== PDF 第 {n} 页 =====\n")
        for line in read_page(doc[idx]):
            print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="规则书结构化抽取")
    ap.add_argument("--build", action="store_true", help="生成结构与分页二次存储")
    ap.add_argument("--pages", nargs="+", type=int, help="打印指定页码的清洗后文本")
    args = ap.parse_args()

    doc = open_doc()
    if args.build:
        dump_structure(doc)
        dump_pages(doc)
    elif args.pages:
        print_pages(doc, args.pages)
    else:
        ap.print_help()
    doc.close()


if __name__ == "__main__":
    main()
