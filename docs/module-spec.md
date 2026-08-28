# 模组识别规范（Mod 抽取管道）

> 本文档定义从「CoC 模组 PDF」到「结构化剧情数据」的抽取规范。
> 与规则书检索（M2）**完全分离**：规则书走 `data/rulebook/` + `retrieval/`，
> 模组走 `data/models/` + 本模块。两者互不依赖。

## 0. 目标

`ModuleExtractor.extract(pdf_path)` 从**一个模组 PDF** 抽取结构化数据，供 KP Agent
主持特定模组时引用。支持**多个模组**分别解析，且**可重复、稳定**地调用。

**核心难点**：模组 PDF 常含**无文字层的图片页**（地图、角色卡、插图、附录图），
纯文本解析（pymupdf `get_text`）无法提取。黑水溪 58 页中 18 页无文字（含地图 p8、
角色卡 p46），必须用 DeepSeek 视觉模型识别。

## 1. 架构

**每页统一「文本读取 + 视觉验证」双轨，不做成本控制。**

对每一页：
1. **文本读取**：pymupdf `get_text()` 抽取文字层（无则空）。
2. **视觉验证**：该页渲染成图片 → DeepSeek 视觉模型识别。

视觉用于补全文字层缺失的地图/角色卡/插图，并与文字层交叉校验；冲突时以文字层为准。

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
├── pdf_reader.py      # pymupdf：render_pages 逐页渲染 PNG + 抽文字层
├── schema.py          # ModuleDocument / Page 数据类（结构化）
├── vision.py          # VisionClient：recognize_page/map/character → JSON
└── extractor.py       # 编排：逐页 文本+视觉 → 合并 → ModuleDocument
```

- `agent/tools.py` 通过 `extract_module(path)` 薄封装调用（供 LLM 加载模组）。
- 视觉客户端复用 `config.Settings` 与 `openai` SDK，不引入新依赖。
- `pdf_reader.py` / `schema.py` 为纯逻辑，**可单测**；`vision.py` 只依赖 LLM。

## 4. 数据结构（schema.py）

```python
@dataclass
class Page:
    index: int                  # 0 起 PDF 页序
    text: str                   # 文字层内容（pymupdf get_text，可为空）
    image_path: str             # 渲染出的 PNG 路径（供视觉复用/审计）
    visual: dict | None = None  # 视觉识别结果（map/character/description）
    content_type: str           # "text" | "map" | "character" | "illustration" | "table"
```

```python
@dataclass
class ModuleDocument:
    source_pdf: str             # 原 PDF 文件名
    title: str | None = None    # 模组名（视觉/文本识别）
    pages: list[Page] = ...
    summary: str = ...          # 总览：本模组剧情一句话
    npcs: list[str] = ...       # 提取到的 NPC 名
    locations: list[str] = ...  # 提取到的地点名
    monsters: list[str] = ...   # 怪物/生物
    sanity_threats: list[str] = ...  # 理智威胁点
    extracted_at: str = ...     # ISO 时间戳
```

> 语义归并（NPC/地点/怪物/理智）由 LLM 识别 + 通用规则（正则匹配：
> `地点\d+`、`NPC`、`理智损失`）辅助。**阶段一先做到「能抽、可回溯」**，
> 语义归类精度留待后续迭代。

## 5. 识别流程（extractor.py）

对每个 PDF：

1. **分页**：`render_pages(pdf, out_dir, dpi)` → 每页渲染 PNG + 抽文字层。
2. **识别页面类型**：`vision.recognize_page` 单次调用 → `content_type`。
3. **按类型精抽取**：
   - `map` → `recognize_map` 抽地名列表。
   - `character` → `recognize_character` 抽角色卡 JSON。
   - `illustration / table / text` → `description`。
4. **合并**：文字层 + 视觉结果 → `Page`；汇总为 `ModuleDocument`。

**稳定性设计**（应对「多模组、可重复调用」）：
- 每模组一份独立输出 JSON（`data/models/<name>.module.json`，gitignored）。
- 单页失败不中断整本：逐页 try/except，失败页标记 `visual` 为空 + 记录错误。
- 幂等重跑：重复解析同一 PDF 覆盖输出，无累积状态。
- 视觉调用注入 `retry`（网络/限流重试），默认 2 次。

## 6. 对外接口

```python
def extract_module(pdf_path: str, *, out_path: str | None = None) -> ModuleDocument:
    """解析一个模组 PDF，返回结构化数据；可选落盘 JSON。"""

def extract_batch(pdf_paths: list[str], out_dir: str | None = None) -> list[ModuleDocument]:
    """批量解析多个模组（黑水溪 / 追书人等）。"""
```

- `extract_batch` 支持用户从 `data/models/` 一次上传/解析多个 PDF。
- 每个 `ModuleDocument` 可序列化 JSON（`to_dict()`），供 `agent/tools.py` 的
  `load_module` 加载进会话。

## 7. 风险与边界

- **成本**：全页视觉+文本双轨，视觉调用量大（已确认不考虑成本控制）。
- **OCR 误差**：角色名/数值可能与原文有出入。文字层存在时以文字层为准，视觉仅补缺失页并交叉校验。
- **敏感内容**：模组可能含恐怖/暴力文本，仅本地解析供 KP 使用，不作公开数据。
- **PDF 源不提交**：`data/**/*.pdf` 已 gitignore（版权源），产出 JSON 也 gitignore。

## 8. 验收标准（对齐「可重复 + 稳定」）

- `extract_module("data/models/入门套装：模组追书人.pdf")`：19 页全部抽取，产出
  结构化文档且**重跑结果一致**（幂等）。
- `extract_module("data/models/[COC模组翻译]黑水溪-Blackwater Creek.pdf")`：
  - 文字层页（40页）文本非空；
  - **图片页**（地图 p8 识别出地名列表；角色卡 p46 识别出属性/技能 JSON）；
  - 单页失败不影响整体（注入坏页仍能返回其余页）。
- `extract_batch([...])` 一次处理多个模组，各自独立输出。
- 纯函数（`pdf_reader` / schema）有单元测试；视觉调用走 mock，不依赖真实网络。
