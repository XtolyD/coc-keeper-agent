# 规则书检索规范（M2 · RAG 分块与索引）

> 本文档定义规则书从「清洗文本」到「可检索规则块」再到「查询」的规范。
> 规则书处理是**离线一次性**的：分块在 `scripts/extract_rules.py --build` 完成（产出
> `rules_chunks.json`），检索在运行时**只加载**语料、不重新分块不读 PDF。
> 模组处理与本流程**完全分离**，另由模组抽取管道负责。

## 0. 目标

`search_rules(query, top_k)` 返回**精准、可回溯页号、可解释**的规则命中，例如：

- 查「奖励骰怎么掷」→ 命中「5.8 奖励骰与惩罚骰」小节块，页 p76-78
- 查「食尸鬼」→ 命中 `name=食尸鬼` 的怪物块，页 p266
- 查「闪避」→ 命中 `name=闪避（一半DEX）` 的技能块，页 p44

## 1. 现状（已落地，规范以此为基）

`rules_chunks.json` 由 `build_chunks.py` 产出，块结构如下：

```json
{
  "type": "skill",            // 实体类型（见 §3）
  "name": "会计（05%）",      // 实体名（标题行首）；rule 类可为空
  "title": "会计（05%）",
  "text": "会计（05%）\n使你理解会计工作的流程…",  // 正文（name 通常为首行）
  "page": 45,                 // 起始 PDF 页（1 起）
  "start_page": 45,           // 页区间起点（跨页块）
  "end_page": 46,             // 页区间终点
  "path": "第四章 技能/4.4 技能列表",  // 章节归属路径
  "order": 0,                 // 全书稳定顺序号
  "lines": ["会计（05%）", "…"]  // 原始行（供 snippet 展示）
}
```

**现状校验**（`verify_chunks.py`）：
- 全书 852 块；有效正文页全部被块覆盖、0 遗漏。
- 除 rule 类少数空名外，实体块均有有效 `name`；`monster/skill/spell` 的
  `text` 以 `name` 开头（name 即该块标题行）。

**残块合并判据**（`merge_fragments.py` / `chunker.py`，规定）：
- 残块合并排除 **CoC 八大属性名**（力量/体质/体型/敏捷/外貌/智力/意志/教育）——
  它们是独立属性标题，不是残块，不得并进上一特征值行尾（否则属性名粘连）。
- 实体名判定排除**以句末标点结尾**的短块（如 `的舞者)｡`、`别的书｡`、`过来查看……`）——
  这些是正文截断残句，不是实体名（真实体名以汉字/字母结尾）。

## 2. 设计原则

1. **按内容实体分块**（非按 TOC 页区间）——分块已是实体粒度，检索单位即实体块。
2. **检索作为独立能力层**，与 agent 编排解耦：
   `retrieval/` 模块负责索引与查询，`agent/tools.py` 的 `search_rules` 只做薄封装调用。
3. **零第三方依赖**：自实现 BM25；中文分词用「字级 unigram + 全角归一」，不引分词库。
4. **可解释**：每次命中返回「命中的关键词 + 各字段得分」，KP 能说明为何命中。
5. **可测**：BM25、分词、打分均为纯函数，可单测；无外部状态。

## 3. 实体类型（EntityType）

| 类型 | 章节来源 | 检索意义 |
|---|---|---|
| `monster` | 第十四章 怪物 | 查「食尸鬼、修格斯、阿萨托斯」→ 怪物数据块 |
| `skill` | 第四章 技能 | 查「闪避、侦查、格斗」→ 技能条目块 |
| `spell` | 第十二章 法术 | 查「放逐术、召唤术」→ 法术块 |
| `combat` | 第六章 战斗 | 查「战技、射击、伤害」→ 战斗规则块 |
| `tome` | 第九章/十一章 典籍 | 查「死灵书、黄衣之王」→ 神话典籍块 |
| `table` | 表Ⅰ~表XVI | 查「伤害加值、武器列表」→ 表格块 |
| `glossary` | 附录Ⅰ 术语表 | 查「护甲、奖励骰」→ 术语词条块 |
| `rule` | 其余章节 | 查「奖励骰、临时疯狂、追逐」→ 通用规则块 |

`type` 用于**查询过滤**：查怪物时可在 `monster` 类型内检索，避免混入「规则/法术」。

## 4. 检索层设计

### 4.1 模块边界

```
src/coc_keeper/retrieval/
├── __init__.py        # 对外暴露 search_rules
├── tokenizer.py       # tokenize(text) -> list[str]（字级 + 全角归一，纯函数）
├── bm25.py            # bm25(query_tokens, doc) -> float（纯函数，零依赖）
├── index.py           # 由 rules_chunks.json 构建索引（离线/懒加载）
└── search.py          # search_rules(query, top_k, type=None) -> list[RuleHit]
```

- `agent/tools.py` 引入 `from ..retrieval import search_rules`，只做参数透传与结果格式化。

### 4.2 中文分词（tokenizer.py）

- 采用**字级 unigram**（逐汉字切分）+ **全角→半角归一**、去空白。
  （零依赖、可解释；不引词典分词库——依据见 `docs/design.md`。）
- 英文/数字（`STR`、`50`、`1D6`）按**连续 ASCII 串**切为一个 token。
- 示例：`奖励骰怎么投 1D100` → `[奖,励,骰,怎,么,投,1d100]`（全角已归一）。

### 4.3 BM25（bm25.py）

自实现标准 BM25（零依赖），参数：
- `k1 = 1.5`、`b = 0.75`、`k3 = 0`（无 query 词频扩展）
- 文档词频、idf、df 从语料统计。

作为**纯函数** `bm25(q_tokens, doc_tokens, df, N, avg_dl) -> float`，便于单测。

### 4.4 字段加权（index.py / search.py）

每个块有两个可检索字段，按**置信度加权**：

- `name`（实体名）：**强字段**，权重更高（`w_name`）。查「食尸鬼」应强命中
  `name=食尸鬼` 的块，而不是正文恰好含这两字的块。
- `text`（正文）：普通字段（`w_text`）。

评分公式（可解释、可配置）：

```python
score = w_name * bm25(q, name_tokens) + w_text * bm25(q, text_tokens)
# w_name = 2.0, w_text = 1.0（可在 config 或 Index 构造时配置）
```

为让「实体名精确命中」不被长文稀释：当 query 完全出现在 `name` 中时，额外给出
`name_exact_bonus`（如 +1.0）。同时记录 `fields = {"name": s_name, "text": s_text}`
供解释。

### 4.5 查询接口（search.py）

```python
@dataclass
class RuleHit:
    type: str
    name: str
    page: int
    start_page: int
    end_page: int
    path: str
    snippet: str       # 命中上下文片段（从 lines 中抽取）
    score: float
    keywords: list[str]  # query 实际命中的关键词
    fields: dict[str, float]  # {"name": x, "text": y} 各字段得分

def search_rules(query: str, top_k: int = 5, type: str | None = None) -> list[RuleHit]:
    ...
    # type 过滤：仅在该 type 内查询（如 type="monster"）
    # 返回按 score 降序的 top_k 个命中；若 query 分词为空则返回 []
```

### 4.6 索引构建（index.py）

- 由 `rules_chunks.json` 在**运行时**构建：`Index(doc)` 读入块 → 统计
  df / 文档长度 / avg_dl，为每块预计算 token 与 idf。
- **不序列化倒排**：862 块规模小，运行时按需构建即可，避免 pickle 脆弱性，
  也更透明、可测、可解释。
- 提供 `Index.from_chunk_file(path)` 与 `Index.build(chunks)` 两种入口。

## 5. 排除清单（不建索引）

由 `build_chunks.py` 已完成的排除，索引层不再重复判断：
- 前言、目录、使用说明、版权页、致谢、译名表、汉化进度表（`_is_excluded_path`）。
- 译名对照表/表格页 → 归为 `table` 块（含在索引中，但 type=table）。
- 译者署名、洛夫克拉夫特引文及署名（清洗层已删）。

## 6. 验收标准（对齐学习计划）

- `search_rules("奖励骰怎么掷")` 命中「奖励骰与惩罚骰」相关块且带页号。
- `search_rules("食尸鬼")` 命中 `name=食尸鬼` 的怪物块、页面正确。
- `search_rules("闪避")` 命中 `name=闪避（一半DEX）` 技能块。
- 每个命中含 `keywords` 与分字段得分，**可解释**。
- 纯函数（tokenizer/bm25）有单元测试，score 计算可复现。

## 7. 对外集成

- `agent/tools.py`：`search_rules` 工具，参数 `{query, type?, top_k?}`，返回
  `[{type,name,page,path,snippet,score}]` 列表（供 LLM 引用并注明页号）。
- 运行时**只加载** `rules_chunks.json`，不读 PDF、不分块；模块惰性构建索引。
