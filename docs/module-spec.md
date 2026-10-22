# 模组导入规范（MinerU + DeepSeek 复核）

> 本文档定义从「CoC 模组 PDF」到「结构化剧情数据」的导入规范。
> 规则书检索（M2）与模组导入**完全分离**：规则书走 `docparser/` + `segments/` + `retrieval/`，
> 模组走 `data/modules/` + `module_pipeline/`。

## 0. 目标与边界

`ModuleImportPipeline.run()` 从一个 PDF 生成 v2 模组：

```text
PDF → MinerU ParseResult → source_chunks → DeepSeek 复核 → 结构分析 → KeeperModule
```

- 只使用 MinerU 解析 PDF；运行时不使用 pymupdf，也不使用 Grok。
- 旧版 `hybrid-vision` 与 v1 `sections` 模组不再兼容，需删除后重新导入。
- 单批失败不丢整本：保留 MinerU 原文并记录 warning。

## 1. 架构

```text
src/coc_keeper/module_pipeline/
├── ports.py           # Protocol: DocumentParser / ModuleReviewer / ModuleAnalyzer
├── mineru_parser.py   # CachedMinerUDocumentParser（按内容 hash 缓存）
├── ingest.py          # ParseResult → source_chunks（纯函数）
├── stat_extractor.py  # 本地属性块抽取（纯函数）
├── review.py          # LLMModuleReviewer（DeepSeek 视觉/文本复核）
├── assembler.py       # source_chunks → KeeperModule
└── pipeline.py        # ModuleImportPipeline 编排
```

`module_service.py` 把流水线、`ModuleStore` 与 `JobManager` 组合为应用服务；Web/CLI 只调用该服务。

## 2. 端口

```python
class DocumentParser(Protocol):
    def parse(self, pdf_path: Path, *, refresh: bool = False) -> ParseResult: ...

class ModuleReviewer(Protocol):
    def review(self, chunks: list[ModuleSourceChunk], parsed: ParseResult) -> ReviewOutcome: ...

class ModuleAnalyzer(Protocol):
    def analyze(self, module: KeeperModule) -> KeeperModule: ...
```

## 3. MinerU 解析

1. `MinerUClient.parse_pdf()` 调用 MinerU API，得到 `ParseResult`。
2. `CachedMinerUDocumentParser` 按 PDF 内容 sha256 缓存到 `data/mineru/<hash>/`。
3. 重新分析默认读缓存；`refresh=True` 强制重新调用 MinerU。
4. `ParseResult.Block` 保留 `text/image/table/header/page_number`、`text_level`、`page_idx`、
   `img_path` 与 `table_body`。

## 4. 原文分块（ingest.py）

`build_source_chunks(parsed, max_pages_per_section=2)`：

- 跳过页眉/页码/脚注噪声。
- `text_level` 非空 = 标题，开启新片段。
- 同一片段最多覆盖 2 页，超出续切。
- `table` 块把 `table_body` 并入正文；`image` 块记录 `img_path`。
- 输出 `ModuleSourceChunk`：
  ```python
  id, heading, page_start, page_end,
  text,       # 初始 = MinerU 原文
  raw_text,   # 审计用 MinerU 原文
  extraction_method = "mineru"
  image_paths: list[str]
  review: dict
  ```

## 5. DeepSeek 复核（review.py）

- 按字符数把 source chunks 分批，附带该页范围内 MinerU 抽出的图片。
- 使用 `VisionClient.review_chunks()`：不传 `thinking`，`max_tokens=393216`，JSON 输出。
- 复核要求：
  - 修正双栏/文本框阅读顺序；
  - 表格用 Markdown 重建；
  - 属性、技能、骰子、护甲、理智损失逐字逐数保留；
  - 无法辨认写 `[无法辨认]`，冲突保留并写 `[待核对]`；
  - 地图提取地名，角色卡提取姓名/属性/技能/武器。
- 输出：
  ```json
  {
    "chunks": [{"id": "...", "text": "...", "issues": [], "confidence": "high"}],
    "images": [{"page": 1, "type": "map|character", "locations": [], "attributes": {}}]
  }
  ```
- 复核成功：`text` = 复核稿，`raw_text` = MinerU 原文，`extraction_method = "mineru+deepseek"`。
- 单批失败：保留原 chunk，记录 warning，整体状态 `partial`。

## 6. 组装与结构分析

`ModuleAssembler.build()`：

- 每个 source chunk → 一个 `ModuleLocation` + `ModuleScene`（页码、摘要、引用）。
- 本地属性块正则抽取 → `ModuleActor`；复核图片中的角色卡/地图并入 actors/locations。
- 生成线性 `StoryGraph`，状态为 `needs-review`。

`LLMModuleAnalyzer.analyze()`：

- 输入复核后的 source chunks（含 MinerU 原文用于交叉核对）。
- 分阶段提取 actors → scenes/locations → story。
- 每阶段做 ID/引用校验；失败批次回退，状态 `partial`。
- 结果保存到 `analysis`：MinerU 信息、复核 warnings/usage、结构分析 usage。

## 7. 数据与状态

`data/modules/<id>.json` 保存 v2 模组，`<id>.pdf` 保存源 PDF；`data/mineru/` 保存解析缓存。
`analysis.status`：

- `needs-review`：MinerU 导入完成，等待人工校对；
- `partial`：部分复核/分析回退；
- `complete`：结构分析完成；
- `failed`：任务失败（不允许创建战役）。

## 8. 验收标准

- 上传 PDF → 后台任务按阶段完成，返回模组。
- 无 `MINERU_API_KEY` 时导入返回明确错误；无 DeepSeek 时仍可生成 MinerU 原文模组。
- 同一 PDF 重新分析命中缓存，不重复调用 MinerU。
- 复核失败不丢整本，warning 可在模组详情查看。
- 旧 `hybrid-vision` / `sections` 模组给出明确“不再支持”错误。
- 所有外部调用可 mock，`pytest -q` 不联网。
