# coc-keeper-agent

> CoC 7th 版跑团 **KP Agent** —— 一名玩家操控一名调查员，AI 担任守秘人（Keeper / KP），
> 主持《克苏鲁的呼唤》（Call of Cthulhu）第七版跑团。
>
> 这也是一个用于**系统性学习 Agent 构建工程**的入门项目：从纯 Python 规则引擎，
> 到 RAG 规则检索，再到工具调用 Agent 与工程化，每一阶段都可独立运行、测试与验收。

---

## 项目定位

跑团（TTRPG）是练习 Agent 工程的理想场景，因为它天然包含 Agent 所需的全部关键能力：

| 跑团需求 | 对应的 Agent 能力 |
| --- | --- |
| 掷骰、判定成功/失败、扣血扣理智 | 确定性**工具调用**（tool calling） |
| 查阅规则书（技能、战斗、理智、法术） | **RAG** 检索增强 |
| 记住角色卡、剧情、NPC、线索 | **记忆与状态管理** |
| KP 叙述剧情、裁决玩家行动 | LLM 的**规划与生成** |
| 规则判定必须正确、可复现 | **评估（eval）与可靠性** |

当前开发主线是完成一次可保存、可继续的单调查员跑团：

1. 创建并保存调查员角色卡，明确职业、技能和当前数值。
2. 导入 PDF 模组，校对人物、地点、场景、线索与剧情分支。
3. 由 AI KP 主持剧情，根据玩家行动选择规则工具并给出叙述。
4. 由工具结算规则与状态变化，可靠保存回合、角色和剧情进度。
5. 分别完成离线回归、供应商冒烟和真实短模组跑团验收。

---

## 目录结构

```
coc-keeper-agent/
├── README.md
├── pyproject.toml            # 打包与 pytest 配置（src 布局）
├── requirements.txt          # 依赖（按里程碑注释）
├── conftest.py               # pytest：src 导入路径 + 脚本化 RNG
├── docs/
│   ├── design.md             # 架构设计（含局部 OOP 边界）
│   ├── learning-plan.md      # 学习路线与里程碑
│   ├── learning-guide.md     # 按代码阅读的具体学习建议
│   ├── docparser-spec.md     # MinerU 解析规范
│   ├── segments-spec.md      # 语义分块规范
│   ├── retrieval-spec.md     # BM25 检索规范
│   ├── skill-data-spec.md    # 技能数据与 SkillCatalog 规范
│   └── module-spec.md        # 模组导入规范（MinerU + DeepSeek 复核）
├── scripts/
│   ├── extract_rules_mineru.py # 规则书 MinerU 抽取/分块
│   ├── extract_skills.py     # 从 xlsx 生成 skills_core.json
│   ├── smoke_llm.py          # LLM 连通性 / 工具调用冒烟测试
│   └── run_evals.py          # 固定种子离线评估
├── data/
│   ├── rulebook/             # 规则全文与 rules_chunks.json（gitignored）
│   ├── mineru/               # MinerU 解析缓存（gitignored）
│   ├── characters/           # 永久角色卡，与模组/战役解耦
│   ├── modules/              # 导入后的 Keeper 私密模组
│   └── campaigns/            # 战役状态与完整对话记录
├── src/coc_keeper/
│   ├── config.py             # 配置：DeepSeek + MinerU
│   ├── cli.py                # 交互式跑团入口
│   ├── dice.py               # 骰子机制
│   ├── character.py          # 角色卡
│   ├── occupations.py        # 229 个职业
│   ├── character_store.py    # 永久角色卡存储
│   ├── module_store.py       # 模组库
│   ├── game_store.py         # 战役与旧回合检索
│   ├── turn_store.py         # 回合与永久角色的协调保存、恢复日志
│   ├── storage.py            # 通用 JSON 记录仓储
│   ├── modules.py            # 模组 v2 领域模型与运行时
│   ├── module_pipeline/      # MinerU 解析 → DeepSeek 复核 → 结构分析
│   ├── module_analysis.py    # DeepSeek 分阶段语义分析
│   ├── module_service.py     # 模组应用服务与后台任务编排
│   ├── skills.py             # 技能目录：别名/基础值/行动候选/检索
│   ├── skill_data.py         # 从 skills_core.json 派生技能基础数据
│   ├── data/
│   │   ├── occupations.json  # 229 个职业模板
│   │   ├── skills_core.json  # 110 条技能事实（xlsx 生成）
│   │   └── skills_playbook.json # 技能使用语义（人工维护）
│   ├── web.py                # FastAPI WebUI/API（含 create_app）
│   ├── web_jobs.py           # 后台任务管理
│   ├── docparser/            # MinerU 客户端与 ParseResult
│   ├── segments/             # content_list → 语义块
│   ├── retrieval/            # 字级 BM25 检索
│   ├── vision/               # DeepSeek 视觉/复核客户端
│   ├── rules/                # 纯函数规则引擎
│   └── agent/
│       ├── tool_schemas.py   #   工具 schema
│       ├── tool_registry.py  #   工具注册表
│       ├── tools.py          #   工具实现与 dispatcher
│       ├── llm.py            #   OpenAI 兼容客户端
│       ├── memory.py         #   对话记忆
│       ├── agent.py          #   工具调用循环
│       ├── prompts.py        #   系统提示词
│       ├── state.py          #   会话状态与存档
│       ├── security.py       #   输入边界与注入防护
│       └── observability.py  #   tracing、token 与成本统计
└── tests/                    # 单元/集成测试
```

---

## 环境搭建（Conda）

项目使用专用 Conda 环境 `coc-keeper`（Python 3.12.13，位于 `C:\Users\XtolyD\.conda\envs\coc-keeper`）：

```powershell
conda create -n coc-keeper python=3.12 pip -y
conda activate coc-keeper
pip install -e ".[dev]"
```

## 快速开始

```powershell
conda activate coc-keeper
cd coc-keeper-agent

# 1. （可选·离线）MinerU 解析规则书 → rules_chunks.json
python scripts\extract_rules_mineru.py --write data\rulebook\rules_chunks.json

# 可选：从本地角色卡 xlsx 重新生成技能事实数据
python scripts\extract_skills.py

# 2. 运行完整测试与离线评估
python -m pytest -q
python -m coc_keeper.cli --eval

# 3. （M3）交互式跑团：需先在 .env 配置 DEEPSEEK_API_KEY
python -m coc_keeper.cli

# 固定随机种子并自动保存战役
python -m coc_keeper.cli --seed 1920 --autosave saves\campaign.json

# 从存档继续
python -m coc_keeper.cli --load saves\campaign.json --autosave saves\campaign.json

# 启动时加载 PDF 模组
python -m coc_keeper.cli --module "D:\Modules\scenario.pdf" --autosave saves\scenario.json
```

CLI 内可使用 `/status`、`/trace`、`/save [路径]` 和 `/help`。
规则层、RAG、存档与离线评估不需要网络；在线 KP Agent 需要 `openai` 与 DeepSeek 密钥；
PDF 导入/重新解析还需要 `MINERU_API_KEY`。

## WebUI

在 `.env` 中配置密钥后启动本地界面：

```powershell
conda activate coc-keeper
cd coc-keeper-agent
coc-keeper-web
```

然后打开 `http://127.0.0.1:8765`。也可以运行：

```powershell
python -m coc_keeper.web
```

WebUI 的推荐流程是：

1. 在“角色卡”中生成五组完整属性并选择一组。
2. 从参考角色卡提取的 229 个职业中选择具体职业，再完成固定、组选和任意本职技能选择。
3. 分别分配职业点和 `INT×2` 兴趣点。职业点按职业公式计算，只能用于本职技能；默认本职/非本职
   上限为 70/60，信用评级必须先用职业点达到该职业范围下限。
4. 永久保存角色卡。角色卡保存在 `data/characters/`，不属于任何模组，可被多个战役重复选择。
5. 在“模组库”中导入 PDF。原始 PDF 会保存在本地模组库；后台依次执行 MinerU 解析、
   DeepSeek 复核、结构分析。单页/单批失败会保留 MinerU 原文并列出待校对警告。
6. 在“检查 / 编辑”中分别校对角色与怪物、地点与场景、故事线和 PDF 原文。
7. 在“战役”中选择一张角色卡和一个模组后开局，由 AI KP 主持。战役保存在 `data/campaigns/`，角色状态变化会同步回永久角色卡。
8. “技能”页可检索技能说明、基础值、使用场景、容易混淆的技能与失败风格；这些数据也供 KP Agent 在跑团中调用。

角色卡、模组和战役是三个独立实体，库列表均提供删除入口。删除战役不会删除它引用的角色卡或模组；
为避免留下无法同步的引用，被战役使用的角色卡和模组需先删除对应战役。模组库修改只影响之后创建的战役，
已开始的战役使用创建时的模组快照，不会被中途改写。
每个回合开始时读取永久角色卡的最新数值，再保存本回合变更；同一角色被多个单人战役使用时，
旧战役也会使用最新角色状态。回合与角色保存使用恢复日志协调，保存失败会恢复原记录。
浏览器为行动生成请求编号，重复提交已完成的编号会返回原回复；待重试编号在当前浏览器会话中保存。
主导航可收成图标栏，战役中的调查员详情也可独立收起。玩家界面和玩家安全 API 均不显示模组场景数量、
当前编号或推进比例；这些结构只在 Keeper 内部保留。

由 KP Agent 根据玩家意图和情境决定是否检定，再调用规则工具。回复顶部汇总已执行检定的项目、骰值、
目标、行动成败与自然成功度。技能知识库提供搜查、潜行、格斗、开锁、交涉和急救等行动的候选技能与说明。

文本主持与视觉识别统一使用 `deepseek-flash`，并显式声明 `1,000,000` token 上下文窗口：

```dotenv
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_CONTEXT_WINDOW=1000000

# MinerU 文档解析（PDF → content_list + images）
MINERU_API_KEY=...
MINERU_BASE_URL=https://mineru.net
```

应用不再设置“整个战役累计 token 上限”。供应商仍会限制单次请求的上下文长度，因此系统会永久保存
完整对话，只把近期完整工具回合和与当前输入相关的旧回合送入模型。这样可持续推进长战役，同时避免破坏
assistant/tool 消息配对。私有 PDF 内容会发送给所配置的模型供应商；使用第三方模型前应确认其数据政策。
DeepSeek 思考模式的工具回合会同步保存并回传 `reasoning_content`；旧存档中缺少该字段的不完整
工具中间消息会在恢复时过滤，已发生的玩家输入和 Keeper 最终叙述仍保留。

## 技能知识

技能数据分两层：

- `src/coc_keeper/data/skills_core.json`：由 `scripts/extract_skills.py` 从角色卡 xlsx 的 `附表` 生成，保存技能名、基础值、说明、难度、孤注一掷与失败示例。
- `src/coc_keeper/data/skills_playbook.json`：人工维护的技能使用语义，记录什么时候用、何时换别的技能、容易混淆的技能与失败风格。

Agent 在跑团中使用：

- `resolve_skill`：玩家行动 → 候选技能（仅供参考，最终由 KP 决定）
- `get_skill`：读取单个技能的完整说明
- `search_skills`：按关键词/类别检索技能
- `roll_skill_check`：自动把别名/子技能解析到角色卡的 canonical 技能

WebUI 的“技能”页提供同样的检索与详情视图。

## PDF 模组

运行中可用以下 Keeper 命令：

```text
/module add D:\Modules\scenario.pdf
/module status
/module next 玩家已找到钥匙并打开地下室
/module export data\modules\scenario-reviewed.json
```

模组 JSON 使用 `version: 2`，将信息分开持久化：

- `actors`：每名 NPC / 怪物的属性、技能、攻击、护甲、理智损失和来源页。
- `locations`：稳定地点信息、氛围、可交互特征和地点连接。
- `source_chunks`：可追溯原文。`text` 保存 DeepSeek 复核稿，`raw_text` 保存 MinerU 原文，
  `extraction_method` 标记来源（`mineru` / `mineru+deepseek` / `manual`）；默认最多两页一块，
  不承担剧情推进职责。
- `scenes`：当前局面、出场实体引用、线索、事件、检定、后果、目标和秘密。
- `story.nodes / story.edges`：明确的剧情大纲、节点和有条件分支。
- `analysis`：MinerU/复核/结构分析的状态、模型、token 用量与回退警告。

导入器只使用 MinerU 解析结果：MinerU 完成双栏、表格、图片和标题层级识别；DeepSeek 在此基础上复核
阅读顺序与表格，并识别地图/角色卡图片；随后 DeepSeek 生成 actors/locations/scenes/story。MinerU 结果按
PDF 内容 hash 缓存在 `data/mineru/<sha256>/`，重新分析默认复用缓存。单批复核失败会保留 MinerU 原文并标记
`partial`；不会丢失整本模组。旧版 `hybrid-vision` 与 v1 `sections` 模组已不再支持，需要删除后重新导入 PDF。

原始 PDF 存在 `data/modules/<模组ID>.pdf`，结构化结果存在同名 `.json`；两者均为 Keeper 私密资料且不会进入 Git。
旧版本已经导入但没有保留 PDF 的模组需要重新上传。运行时只使用 MinerU + DeepSeek 复核管道，不再使用 pymupdf
或 Grok 解析 PDF。

新战役从剧情图声明的入口节点开始。模组运行时只把当前剧情节点对应的场景、地点、出场实体与原文片段送给 Agent；`search_module` 不读取其他节点。
分析时保留精确原文块引用；缺失且无法唯一定位的引用标记为待校对，当前上下文暂不注入该场景的原文摘录。
同一原文块可能包含多个场景，正式开跑前仍需校对块的范围。语义无效的场景分析按批次回退，保留其他成功批次。
`advance_module` 只能沿当前节点的可用边推进，多分支时必须选择由玩家行动实际触发的 `next_node_id`。
系统提示和最终输出门禁共同阻止完整剧情、未来秘密和结局泄露。`data/modules/*.json`、同名 `.pdf` 与 `saves/`
已被 Git 忽略，因为两者都包含 Keeper 私密内容，不应发给玩家。

---

## 里程碑状态

| # | 里程碑 | 内容 | 状态 |
| --- | --- | --- | --- |
| M0 | 规则引擎核心 | 骰子、角色卡、技能/对抗/幸运/理智检定 | 已完成 |
| M1 | 规则引擎扩展 | 战斗、射程、伤害/护甲、疯狂状态机、追逐、治疗 | 已完成 |
| M2 | 规则检索 RAG | MinerU 解析 + 语义分块 + 纯 Python BM25、可解释页码引用 | 已完成 |
| M3 | KP Agent 核心 | 工具调用循环、记忆、规则查询、单人 CLI | 已完成；真实供应商需单独冒烟 |
| M4 | 单调查员会话与存档 | 调查员状态、剧情进度、JSON 保存与恢复 | 已实现；随主流程回归验收 |
| M5 | 工程化 | 固定种子 eval、tracing、token/成本、输入安全、CLI | 已完成 |
| M6 | PDF 模组 | MinerU 解析、DeepSeek 复核、当前场景检索、图结构推进、防剧透 | 已完成 |
| M7 | 本地 WebUI | 永久角色卡、五组选卡、技能加点、模组库与独立战役 | 已完成 |
| M8 | 职业建卡 | Excel 职业目录、职业公式、双点池、信用评级与 70/60 上限 | 已完成 |
| M9 | 结构化模组 | MinerU + DeepSeek 复核、NPC/怪物/地点/场景拆分、剧情图、后台任务 | 已完成 |

详细的学习路线见 [`docs/learning-plan.md`](docs/learning-plan.md)，按代码阅读的建议见
[`docs/learning-guide.md`](docs/learning-guide.md)，架构设计见 [`docs/design.md`](docs/design.md)。

在线验收边界：仓库不保存 API 密钥，也不把私有规则书全文提交到 Git。`scripts/smoke_llm.py`
和 `scripts/extract_rules_mineru.py` 分别用于在本机配置就绪后验证这两项外部资源。

前端请求去重回归可在安装 Node.js 后运行 `node --test tests/test_web_frontend.js`。
最近的缺陷修复与验证结果见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 规则依据

本项目规则严格依据《COC7th 核心规则书 v1.2.1》，所有判定均已对照规则书核实，
关键出处以注释形式写在对应模块的 docstring 中（如「表Ⅰ：伤害加值和体格表」、
「游戏系统摘要」p358 等）。规则的**正确性由单元测试锁定**，不依赖 LLM 记忆。
