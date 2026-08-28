# -*- coding: utf-8 -*-
"""规则书（MinerU 版）抽取：分批解析 → segments 分块 → rules_chunks.json。

取代旧 pymupdf 几何管道（rulebook.py/merge_fragments.py/build_chunks.py/chunker.py）。
流程（docparser + segments，见 docs/docparser-spec.md / segments-spec.md）：
1. MinerU 分批解析规则书（单次 ≤200 页，380 页分 2 批：1-200 / 201-380）。
2. 合并各批的 content_list blocks（page_idx 基于原 PDF，自然连续）。
3. chunk_content_list(blocks, type_fn=rulebook_type_fn) 分块。
4. 写 data/rulebook/rules_chunks.json（字段对齐旧格式，供 retrieval.Index 消费）。

用法：
    python scripts/extract_rules_mineru.py --write data/rulebook/rules_chunks.json
    python scripts/extract_rules_mineru.py --pages 26 27   # 打印某页分块（验证）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz  # pymupdf（仅用于读页数，不参与分块）

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from coc_keeper.docparser import MinerUClient  # noqa: E402
from coc_keeper.docparser.result import parse_content_list  # noqa: E402
from coc_keeper.segments import chunk_content_list, rulebook_type_fn  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebook"
PDF = DATA_DIR / "COC7th核心规则书v1.2.1.pdf"
OUT_CHUNKS = DATA_DIR / "rules_chunks.json"

# MinerU 精准 API 单次 ≤200 页；规则书 380 页分 2 批
BATCH_PAGES = 200


def _doc_page_count() -> int:
    doc = fitz.open(str(PDF))
    n = doc.page_count
    doc.close()
    return n


def _iter_batches(page_count: int):
    """按 BATCH_PAGES 切成 (start, end) 区间（1 起闭区间）。"""
    start = 1
    while start <= page_count:
        end = min(start + BATCH_PAGES - 1, page_count)
        yield start, end
        start = end + 1


def parse_all(client: MinerUClient, page_count: int):
    """分批解析全书，合并 blocks（page_idx 基于原 PDF，自然连续）。

    MinerU 产物的临时目录用完即弃（避免 /tmp 堆积）。
    """
    import shutil
    import tempfile

    merged_blocks = []
    workdir = tempfile.mkdtemp(prefix="rules_mineru_")
    try:
        for start, end in _iter_batches(page_count):
            ranges = f"{start}" if start == end else f"{start}-{end}"
            print(f"[docparser] 解析页 {ranges} ...")
            result = client.parse_pdf(str(PDF), page_ranges=ranges, out_dir=workdir)
            # 从落盘的 content_list 解析（保持 img_path 等完整字段）
            import json as _json
            data = _json.load(open(result.content_list_path, encoding="utf-8"))
            merged_blocks.extend(parse_content_list(data))
            print(f"[docparser] 批次 {ranges} → {len(data)} 块（累计 {len(merged_blocks)}）")
        return merged_blocks
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def build_chunks(blocks) -> list[dict]:
    """分块 → Chunk.to_dict()（对齐 rules_chunks.json 字段）。"""
    chunks = chunk_content_list(blocks, type_fn=rulebook_type_fn)
    return [c.to_dict() for c in chunks]


def write_chunks(chunks: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {len(chunks)} 块写入 {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="规则书 MinerU 抽取")
    ap.add_argument("--write", type=str, help="写入 rules_chunks.json 的路径")
    ap.add_argument("--pages", nargs="+", type=int, help="打印指定页的分块（验证）")
    args = ap.parse_args()

    if not PDF.exists():
        sys.exit(f"规则书不存在: {PDF}")

    page_count = _doc_page_count()
    print(f"规则书 {page_count} 页，MinerU 分批解析")
    client = MinerUClient()
    blocks = parse_all(client, page_count)
    print(f"[ok] 全书解析累计 {len(blocks)} blocks")

    chunks = build_chunks(blocks)

    if args.write:
        write_chunks(chunks, Path(args.write))
    if args.pages:
        _print_pages(chunks, args.pages)


def _print_pages(chunks: list[dict], pages: list[int]) -> None:
    print("\n=== 指定页分块 ===")
    for pg in pages:
        rel = [c for c in chunks if c.get("start_page", c["page"]) <= pg <= c.get("end_page", c["page"])]
        print(f"【页 {pg}】")
        for c in rel:
            print(f"  [{c['type']}] {c['name'][:26]!r:30s} {len(c['lines'])}行 页{c['start_page']}-{c['end_page']}")
        if not rel:
            print("  (无块)")
        print()


if __name__ == "__main__":
    main()
