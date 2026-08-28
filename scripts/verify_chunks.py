# -*- coding: utf-8 -*-
"""规则书「内容实体」分块：全书逐页验证报告。

输出每一页切出的实体块（type + name + 行数 + 字数），并汇总统计与异常提示。
用于人工逐页校验「实体识别」是否精准（方案 B 的验证环节）。

离线一次性运行，产出 text 报告到 stdout 或文件。

用法：
    python scripts/verify_chunks.py            # 打印全书逐页块报告
    python scripts/verify_chunks.py --pages 14 252 253   # 只打印指定页
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from coc_keeper.rulebook import (  # noqa: E402
    build_page_path_map, build_structure, read_page,
)
from coc_keeper.build_chunks import chunk_pages  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebook"
PDF = DATA_DIR / "COC7th核心规则书v1.2.1.pdf"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", nargs="+", type=int, help="仅打印指定页")
    ap.add_argument("--out", type=str, help="写入文件的路径（否则打印到 stdout）")
    args = ap.parse_args()

    if not PDF.exists():
        sys.exit(f"规则书不存在: {PDF}")
    doc = fitz.open(str(PDF))
    pages = {i + 1: read_page(doc[i]) for i in range(doc.page_count) if read_page(doc[i])}
    secs = build_structure(doc)
    pagemap = build_page_path_map(secs)
    chunks = chunk_pages(pages, pagemap)

    lines: list[str] = []
    lines.append(f"规则书实体分块报告 —— {len(doc)} 页，产出 {len(chunks)} 个块\n")

    # 统计
    from collections import Counter
    type_count = Counter(c["type"] for c in chunks)
    lines.append("== 块类型统计 ==")
    for t, n in type_count.most_common():
        lines.append(f"  {t:<9} {n}")
    lines.append(f"  {'总计':<8} {len(chunks)}\n")

    # 逐页：把每个块归属到其页区间（跨页块在多页都显示）
    for page_no in sorted(pages):
        if args.pages and page_no not in args.pages:
            continue
        path = pagemap.get(page_no, "")
        page_chunks = [c for c in chunks
                       if c.get("start_page", c["page"]) <= page_no <= c.get("end_page", c["page"])]
        lines.append(f"【第 {page_no} 页】 path={path!r}")
        for c in page_chunks:
            nm = c["name"] or "(无名字)"
            pr = c.get("page_range") or (c.get("start_page", c["page"]), c.get("end_page", c["page"]))
            prange = f"页{pr[0]}-{pr[1]}" if pr[1] != pr[0] else f"页{pr[0]}"
            lines.append(f"    [{c['type']:<7}] {nm[:26]:<28} {len(c['lines']):>3}行 {len(c['text']):>5}字 {prange}")
        if not page_chunks:
            lines.append("    (无块 —— 可能为纯图/空页/或排除的章节)")
        lines.append("")

    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(report)
    doc.close()


if __name__ == "__main__":
    main()
