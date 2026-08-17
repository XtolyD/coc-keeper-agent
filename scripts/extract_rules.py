# -*- coding: utf-8 -*-
"""从 CoC 7th 核心规则书 PDF 抽取文本，供设计参考与后续 RAG 使用。

用法:
    python scripts/extract_rules.py --toc            # 仅打印目录结构
    python scripts/extract_rules.py --dump-all       # 抽取全文到 data/rulebook/fulltext.txt
    python scripts/extract_rules.py --pages 10 12    # 打印指定页码范围文本
"""
import argparse
import sys
from pathlib import Path

import fitz  # pymupdf

# 统一 UTF-8 输出，避免 Windows 控制台 GBK 编码问题
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PDF_PATH = Path(r"C:\Users\XtolyD\Desktop\COC7th核心规则书v1.2.1.pdf")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebook"


def open_doc():
    if not PDF_PATH.exists():
        sys.exit(f"规则书不存在: {PDF_PATH}")
    return fitz.open(str(PDF_PATH))


def print_toc():
    doc = open_doc()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "toc.txt"
    lines = [f"总页数: {doc.page_count}", f"目录条目数: {len(doc.get_toc())}", ""]
    for lvl, title, page in doc.get_toc():
        indent = "  " * (lvl - 1)
        lines.append(f"{indent}[{lvl}] {title}  ->  p{page}")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写入 {out}")


def dump_all():
    doc = open_doc()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "fulltext.txt"
    with out.open("w", encoding="utf-8") as f:
        for i in range(doc.page_count):
            text = doc[i].get_text("text")
            f.write(f"\n===== 第 {i + 1} 页 =====\n")
            f.write(text)
    print(f"已写入 {out}（{doc.page_count} 页）")


def print_pages(start, end):
    doc = open_doc()
    for i in range(start - 1, min(end, doc.page_count)):
        print(f"\n===== 第 {i + 1} 页 =====\n")
        print(doc[i].get_text("text"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--toc", action="store_true")
    ap.add_argument("--dump-all", action="store_true")
    ap.add_argument("--pages", nargs=2, type=int)
    args = ap.parse_args()
    if args.toc:
        print_toc()
    elif args.dump_all:
        dump_all()
    elif args.pages:
        print_pages(*args.pages)
    else:
        ap.print_help()
