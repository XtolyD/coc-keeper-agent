# 文档解析规范（DocParser · MinerU）

> 本文档定义「PDF → 结构化内容」的解析规范，统一服务规则书与模组书。
> 由 MinerU 在线 API 完成**版面理解**（双栏/表格/图片/标题层级/页号），
> 产出 `content_list.json`（按块、带类型/层级/页号/坐标）供上层手动 RAG 分块。
> 与 `retrieval/`（BM25 检索）、`vision/`（DeepSeek 图片分析）解耦。

## 0. 定位与分工

**MinerU 只做「PDF → 结构化」**，不做检索、不做语义归类。三层各司其职：

| 层 | 模块 | 职责 |
|---|---|---|
| 文档解析 | `docparser/` | PDF → `content_list.json` + 图片（MinerU API） |
| 检索分块 | `retrieval/chunker` | `content_list` → 语义块（type/name/text/page）→ BM25 |
| 图/语义 | `vision/` + `module/` | 分析 MinerU 抽出的图片（DeepSeek 视觉）；模组语义归并 |

**为什么引入 MinerU**：此前规则书用 pymupdf 几何启发式（坐标/字号分级）+ 补丁
（`ATTR_NAMES`、标点结尾排除）来强撑版面理解，对不规则模组书不可持续。
MinerU 直接输出**语义化、分层级、带页号**的结构，根除补丁来源。

## 1. API 流程（已实调验证）

MinerU 精准解析 API（`v4`，用 `.env` 的 `MINERU_API_KEY`），本地文件走批量上传：

```
┌──────────────┐   POST /api/v4/file-urls/batch   ┌───────────────────┐
│ 申请上传链接  │ ──────────────────────────────▶ │ batch_id + file_urls[]│
└──────────────┘                                   └─────────┬─────────┘
                                                              │ PUT 上传本地文件
                                                              ▼
┌──────────────┐   GET /api/v4/extract-results/batch/{id}  ┌──────────────┐
│ 轮询结果     │ ◀───────────────────────────────────── │ 系统自动提交解析│
└──────┬───────┘                                          └──────────────┘
       │ state=done → full_zip_url
       ▼
   下载 zip → full.md + *_content_list.json + images/
```

**端点**（base `https://mineru.net`）：
- `POST /api/v4/file-urls/batch`：申请上传链接。body = `{model_version, enable_formula, enable_table, language, files:[{name, is_ocr?, page_ranges?}]}`
- `PUT {file_urls[i]}`：上传本地文件（无 `Content-Type`）
- `GET /api/v4/extract-results/batch/{batch_id}`：轮询，返回 `data.extract_result: [{file_name, state, err_msg, full_zip_url}]`

**参数**：
- `model_version`：`pipeline`(默认) / `vlm`(推荐) / `MinerU-HTML`
- `enable_formula`（默认 true）、`enable_table`（默认 true）、`language`（默认 ch）
- `files[].name`：文件名（须含正确后缀）；`is_ocr`；`page_ranges`（如 `"2,4-6"`）

**状态**：`done`(完成) / `waiting-file` / `pending` / `running` / `failed` / `converting`

## 2. 解析产物（zip 内容）

| 文件 | 作用 |
|---|---|
| `full.md` | 完整 Markdown 结果 |
| `*_content_list.json` | **结构化内容（分块主输入）** |
| `*_content_list_v2.json` | 变体（结构同 v1） |
| `*_model.json` | 模型输出（暂不用） |
| `layout.json` | 版面布局（暂不用） |
| `images/*.jpg` | MinerU 提取出的图片（供 `vision/` 分析） |
| `*_origin.pdf` | 原 PDF 副本 |

**`content_list.json` 元素结构**：
```json
{"type": "text", "text": "第三卷", "text_level": "2", "bbox": [326,125,673,237], "page_idx": "0"}
```
- `type`：`text` / `image` / `table` / `header` / `page_number`
- `text_level`：标题层级（`"2"`=二级标题；空=正文）；仅 text 类型有
- `page_idx`：页号（0 起）
- `bbox`：块坐标 [x0,y0,x1,y1]（供排序/页内定位）
- **`img_path`**：图片相对路径（`type=image` 时，如 `images/xxx.jpg`）——供 vision 分析
- 按页顺序排列（`page_idx` 单调递增），已按阅读顺序

## 3. 模块边界

```
src/coc_keeper/docparser/
├── __init__.py        # 暴露 parse_pdf / MinerUClient
├── client.py          # MinerU API：申请/上传/轮询/下载（用 MINERU_API_KEY）
├── result.py          # ParseResult / Block 数据类（解析产物）
└── cache.py           # 缓存：避免重复解析同一 PDF（可选，按内容 hash）
```

- 复用 `config.Settings` 读 `MINERU_API_KEY`（密钥只在 config 读，不打印）。
- 纯 I/O + 数据类，**可注入 base_url 便于单测**（mock requests）。
- 不依赖 `retrieval/` / `vision/` / `module/`——只输出结构，不消费别层。

## 4. 数据类（result.py）

```python
@dataclass
class Block:
    type: str            # text/image/table/header/page_number
    text: str            # 文本（image 为空）
    text_level: str      # 标题层级（"" 正文）
    page_idx: int        # 页号（0 起）
    bbox: list[float]    # [x0,y0,x1,y1]
    img_path: str        # 图片相对路径（type=image 时，供 vision 分析）

@dataclass
class ParseResult:
    source_pdf: str      # 原 PDF 名（含路径）
    blocks: list[Block]  # content_list.json 解析后的块（有序）
    markdown: str        # full.md 全文
    images_dir: str      # 图片本地目录（images/）
    parsed_at: str       # ISO 时间戳

    def to_dict(self) -> dict: ...
```

## 5. 对外接口（client.py）

```python
class MinerUClient:
    def __init__(self, api_key=None, base_url="https://mineru.net"):
        ...

    def parse_pdf(self, pdf_path, *, model_version="vlm",
                  enable_formula=False, enable_table=True,
                  language="ch", poll_interval=8, timeout=300) -> ParseResult:
        """解析一个 PDF（申请→上传→轮询→下载），返回 ParseResult。

        - 本地 PDF 走 file-urls/batch 上传流程。
        - 轮询直到 state=done/failed；失败抛 DocParserError。
        - 幂等：同 PDF 可重复调用（re-解析），不维护跨调用状态。
        """
```

## 6. 稳定性设计（应对模组书重复调用）

- **幂等**：每次 `parse_pdf` 独立申请 batch，不跨调用累积；重复解析同 PDF 覆盖产物。
- **失败可重试**：轮询超时/网络错误抛 `DocParserError`，调用方可重试。
- **下载解压到本地目录**（供 vision 分析图片），目录名用 batch_id 隔离。
- **不序列化**：MinerU 产物是 API 返回值，不落中间态到项目（图片/zip 在临时/数据目录，gitignore）。

## 7. 风险与边界

- **成本**：每次解析一次 API 调用（不考虑成本控制，用户已确认）。规则书一次性，模组书按需。
- **文件限制**：精准 API ≤200MB / ≤200页；批量 ≤200 文件。超限需切分或走 agent API。
- **图片依赖 vision**：MinerU 只抽取图片**不分析**；`type=image` 块需交 DeepSeek 视觉理解。
- **密钥**：`MINERU_API_KEY` 在 `.env`，只在 config 读，绝不打印/硬编码。
- **生成物**：MinerU 下载的 zip/图片不提交 git（gitignore `data/**` 解析产物）。

## 8. 验收标准

- 对**任意** PDF：`parse_pdf(<pdf_path>)`：
  - 返回 ParseResult，`blocks` 非空，含 `type/page_idx/text_level/bbox`。
  - `markdown` 非空，`images_dir` 含 MinerU 抽出的图片。
- `type=image` 的块存在（地图/插图被正确识别为 image 而非 text）。
- 单测：MinerUClient 用 mock 的 requests 验证「申请→上传→轮询→下载」调用链；
  纯函数（Block 解析、state 判定）可单测、可复现。
- 密钥不打印；无硬编码 base_url/key。

> 「任意 PDF」指：spec 不绑定特定模组名，验收以上传的真实模组/规则书为准（见 `data/models/`）。
