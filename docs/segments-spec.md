# 语义分块规范（Segments · MinerU content_list → 可检索块）

> 本文档定义「MinerU content_list → 语义块」的通用分块规范，统一服务规则书与模组书。
> 分块器只从 `docparser.Block`（content_list）分块，不关心章节来源、不与书本耦合。
> 产物直接喂给 `retrieval.Index`（BM25 检索）。

## 0. 定位

MinerU 已把 PDF 版面理解成结构化内容（块/层级/页号/坐标）。**分块器在其上做 RAG 分块**：
- 输入：`docparser.Block` 列表（`type`/`text`/`text_level`/`page_idx`/`bbox`）
- 输出：语义块 `Chunk` 列表（字段对齐 `rules_chunks.json`，可被 `Index.build` 消费）

**不做的**：不判语义类型（由调用方注入 `type_fn`）、不做检索、不依赖任何书。

## 1. 分块信号（来自 MinerU，比几何启发式可靠）

| content_list 块 | 信号 | 分块动作 |
|---|---|---|
| `type=text` + `text_level` 非空 | 标题 | **新块边界**；标题层级重建章节 `path` |
| `type=text` + `text_level` 空 | 正文 | 累积进当前块 |
| `type=table` / `image` | 特殊块 | **独立成块**（截止当前正文块） |
| `type=header` / `page_footnote` / `page_number` | 噪声 | 跳过（不参与内容/检索） |
| `page_idx` | 页号 | 记块 `page`；跨页块取起止页 |

**标题栈重建 path**：`text_level` 是标题层级（`1`=章，`2`=节…），用栈维护，如
`克苏鲁的呼唤 第七版/使用说明/规则书翻译`。

## 2. 输出 Chunk（字段对齐 rules_chunks.json）

```python
@dataclass
class Chunk:
    type: str         # rule/skill/spell/combat/monster/tome/table/glossary/image
    name: str         # 块标题（正文块可为空）
    title: str        # 原始标题
    text: str         # 正文（含 name 首行）
    page: int         # 起始页（1 起）
    start_page: int
    end_page: int
    path: str = ""    # 章节路径（标题栈重建）
    order: int = 0
    lines: list[str]  # 原始行（供 snippet）
```

`to_dict()` 产出与 `rules_chunks.json` 一致的字段，可直接 `Index.build(chunks_dict)`。

## 3. 类型判定：可注入 type_fn

分块器本身不判语义类型（通用），由调用方注入：

```python
chunk_content_list(blocks, type_fn=None)   # 默认全 rule
chunk_content_list(blocks, type_fn=rulebook_type_fn)  # 规则书按章节关键词
```

- `type_fn(path, name) -> str`：给 `path`/`name` 判类型。
- `rulebook_type_fn`：按章节路径关键词（技能→skill、法术→spell、怪物→monster…），供规则书管道。
- **`table`/`image` 块类型固定**（由块类型决定，不走 `type_fn`）。
- 默认（模组书）全 `rule`——模组书不按规则书章节分类型。

## 4. 与 retrieval 衔接

```
MinerU content_list (docparser.Block)
  → chunk_content_list(blocks, type_fn)   (segments)
  → Chunk.to_dict() 列表
  → Index.build(dicts)                    (retrieval)
  → search_rules(query)                   (BM25)
```

`Index.build` 用 `name`/`text`，`search.py` 用 `type/name/page/start_page/end_page/path/lines`
——`Chunk.to_dict()` 恰好提供这些字段，**无缝衔接**。

## 5. 模块边界

```
src/coc_keeper/segments/
├── __init__.py        # 暴露 Chunk / chunk_content_list / rulebook_type_fn
└── chunker.py         # 分块算法（纯函数、可单测、type_fn 可注入）
```

- 不依赖 `module/`（模组语义）、`retrieval/`（检索）。只复用 `docparser.Block` 数据类。
- 与旧 `chunker.py`（几何启发式分块）**无关**——后者是规则书旧管道，将被 MinerU 管道取代。

## 6. 验收标准

- `chunk_content_list(blocks)` 产出的块含 `type/name/text/page/start_page/end_page/path/lines`。
- 标题 `text_level` 正确开新块、重建 `path`；正文累积、跨页 `start/end_page` 正确。
- 噪声块（header/footnote/page_number）被跳过；table/image 独立且不吞正文。
- 可注入 `type_fn`：默认全 rule；`rulebook_type_fn` 按章节关键词定 skill/spell/monster。
- `Chunk.to_dict()` 可直接 `Index.build` → `search_rules` 检索（端到端命中并带页号）。
- 纯函数、单测可复现（不联网）。
