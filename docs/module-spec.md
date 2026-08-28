# 模组识别规范（Mod 抽取管道）

> 本文档定义从「CoC 模组 PDF」到「结构化剧情数据」的抽取规范。
> 与规则书检索（M2）**完全分离**：规则书走 `data/rulebook/` + `retrieval/`，
> 模组走 `data/models/` + 本模块。两者互不依赖。

## 0. 目标

`ModuleExtractor.extract(pdf_path)` 从**一个模组 PDF** 抽取结构化数据，供 KP Agent
主持特定模组时引用。支持**多个模组**分别解析，且**可重复、稳定**地调用。

**核心难点**：模组 PDF 常含**无文字层的图片页**（地图、角色卡、插图等），
纯文本解析无法提取，须用 DeepSeek 视觉分析 MinerU 抽出的图片块。

## 1. 架构（MinerU + vision）

**MinerU 做版面理解，DeepSeek 视觉做图片分析。**

流程：
1. **docparser（MinerU）**：`parse_pdf` 解析 PDF → `ParseResult`（content_list
   text 块/图片块 + images/）。
2. **text 块**：直接用 MinerU 文本（不消耗视觉）。
3. **image 块**：取 `img_path` → DeepSeek 视觉识别（地图地名/角色卡数值/插图描述），
   失败不中断整本。

`ModuleExtractor` 以 `ParseResult` 为输入（`extract_from_result`），纯逻辑可测。
不做成本控制：每个 image 块都交视觉。

## 2. 视觉调用约束（必须遵守）

1. **不传 `thinking`**——用默认（模型按需决定是否思考）。
2. **`max_tokens = 393216`**（`deepseek-v4-flash-vision-exp` 的 API 上限）。
3. **JSON 输出**：`response_format={"type": "json_object"}`。
4. **图片输入**：`content` 为块数组，图片用 `image_url`（base64 data URL 内联）。
5. **OCR 校正**：地图地名/角色卡数值可能与原文有出入。文字层存在时以文字层为准，
   视觉结果作补充；两者冲突需标记。

> 以上参数为实测验证的定案，依据见 `docs/design.md`「模组识别（Mod）决策」。

## 3. 模块边界

```
src/coc_keeper/module/
├── __init__.py        # 对外暴露 ModuleExtractor / extract_module
├── schema.py          # ModuleDocument 数据类（结构化）
└── extractor.py       # 编排：docparser ParseResult → 逐块 text/画像 → ModuleDocument
```

依赖的外部层（均为独立能力）：
- `docparser/`：MinerU 解析（`parse_pdf` → ParseResult）。
- `vision/`：DeepSeek 视觉（`VisionClient` 分析 image 块）。
- `segments/`：语义分块（如需从 ParseResult 分块检索，可选）。

- `agent/tools.py` 通过 `extract_module(path)` 薄封装调用（供 LLM 加载模组）。
- `extractor.py` 可注入 mock `VisionClient` 供单测（不联网）。

## 4. 数据结构（schema.py）

```python
@dataclass
class ModuleDocument:
    source_pdf: str             # 原 PDF 文件名
    title: str | None = None    # 模组名（文本/视觉识别）
    summary: str = ""           # 剧情一句话总览
    npcs: list[str] = ...       # 提取到的 NPC 名
    locations: list[str] = ...  # 提取到的地点名
    monsters: list[str] = ...   # 怪物/生物
    sanity_threats: list[str] = ...  # 理智威胁点
    extracted_at: str = ""     # ISO 时间戳
    image_results: list[dict] = ...  # 图片块视觉结果（地图/角色卡/插图），含 page_idx
    text_count: int = 0         # 文本块数（供统计）
```

> 语义归并（NPC/地点/怪物/理智）由视觉识别（image 块）+ 文本启发辅助。
> **阶段先做到「能抽、可回溯」**，语义归类精度留待后续迭代。

## 5. 识别流程（extractor.py）

对每个 PDF：

1. **docparser**：`MinerUClient.parse_pdf` → `ParseResult`（blocks + images/）。
2. **text 块**：直接用 MinerU 文本（不消耗视觉）。
3. **image 块**：取 `img_path` → `vision.recognize_page` 判类型，再按类型精抽取：
   - `map` → `recognize_map` 抽地名列表。
   - `character` → `recognize_character` 抽角色卡 JSON。
   - `illustration / table` → `description`。
4. **合并**：文本块拼接 + 视觉结果 → `ModuleDocument`。

**稳定性设计**（应对「多模组、可重复调用」）：
- 每模组一份独立输出 JSON（`data/models/<name>.module.json`，gitignored）。
- 单图识别失败不中断整本：逐 image 块 try/except，失败跳过该块。
- 幂等重跑：重复解析同一 PDF 覆盖输出，无累积状态。
- 视觉调用注入 `retry`（网络/限流重试），默认 2 次。

## 6. 对外接口

```python
def extract_module(pdf_path: str, *, out_path: str | None = None) -> ModuleDocument:
    """解析一个模组 PDF，返回结构化数据；可选落盘 JSON。"""

def extract_batch(pdf_paths: list[str], out_dir: str | None = None) -> list[ModuleDocument]:
    """批量解析多个模组（任意上传的模组 PDF）。"""
```

- `extract_batch` 支持用户从 `data/models/` 一次上传/解析多个 PDF。
- 每个 `ModuleDocument` 可序列化 JSON（`to_dict()`），供 `agent/tools.py` 的
  `load_module` 加载进会话。

## 7. 风险与边界

- **成本**：每个 image 块都交视觉（已确认不考虑成本控制）。
- **OCR 误差**：角色名/数值可能与原文有出入。MinerU text 块为准，视觉补图片块并交叉校验。
- **敏感内容**：模组可能含恐怖/暴力文本，仅本地解析供 KP 使用，不作公开数据。
- **PDF 源不提交**：`data/**/*.pdf` 已 gitignore（版权源），产出 JSON 也 gitignore。
- **spec 不绑定模组**：规范用占位符，验收以上传的真实模组为准（见 `data/models/`）。

## 8. 验收标准（对齐「可重复 + 稳定」）

- 对**任意**上传的模组 PDF：`extract_module(<pdf_path>)` 产出 ModuleDocument 且
  **重跑结果一致**（幂等）。
- text 块：MinerU 文本非空（不消耗视觉）；image 块：`img_path` 存在且触发视觉。
- **图片块**可识别：地图抽出地名、角色卡抽出属性/技能 JSON、插图给出描述。
- 单图失败不影响整体：某 image 块识别失败，其余页/块仍返回。
- `extract_batch([...])` 一次处理多个模组，各自独立输出。
- 纯函数（schema / extract_from_result）有单元测试；视觉调用走 mock，不依赖真实网络。

> 「任意模组」指：spec 不绑定具体模组名，验收以上传的真实模组为准（见 `data/models/`）。
