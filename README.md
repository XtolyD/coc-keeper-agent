# coc-keeper-agent

> CoC 7th 版跑团 **KP Agent** —— AI 充当守秘人（Keeper / KP），主持单人或多人的
> 《克苏鲁的呼唤》（Call of Cthulhu）第七版跑团。
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

---

## 目录结构

```
coc-keeper-agent/
├── README.md
├── pyproject.toml            # 打包与 pytest 配置（src 布局）
├── requirements.txt          # 依赖（按里程碑注释）
├── conftest.py               # pytest：src 导入路径 + 脚本化 RNG
├── docs/
│   ├── design.md             # 架构设计
│   ├── learning-plan.md      # 学习路线与里程碑
│   └── learning-guide.md     # 按代码阅读的具体学习建议
├── scripts/
│   ├── extract_rules.py      # 从规则书 PDF 抽取文本（供 RAG）
│   ├── smoke_llm.py          # LLM 连通性 / 工具调用冒烟测试
│   └── run_evals.py          # 固定种子离线评估
├── data/
│   ├── rulebook/             # 抽取出的规则全文（gitignored，可再生成）
│   ├── characters/           # 永久角色卡，与模组/战役解耦
│   ├── modules/              # 导入后的 Keeper 私密模组
│   └── campaigns/            # 战役状态与完整对话记录
├── src/coc_keeper/
│   ├── __init__.py
│   ├── config.py             # 配置：从 .env 读取模型与运行参数
│   ├── cli.py                # 交互式跑团入口（python -m coc_keeper.cli）
│   ├── dice.py               # 骰子机制：d100、奖励/惩罚骰、成功度、难度
│   ├── character.py          # 角色卡：属性、衍生属性、技能、建卡
│   ├── occupations.py        # 229 个职业、职业点公式与本职技能约束
│   ├── character_store.py    # 永久角色卡存储
│   ├── module_store.py       # 模组库
│   ├── game_store.py         # 战役、完整记录与旧回合检索
│   ├── web.py                # FastAPI WebUI/API
│   ├── evaluation.py         # 硬指标评估 + 叙事 rubric
│   ├── scenarios.py          # 端到端规则验收场景
│   ├── modules.py            # PDF 模组导入、顺序推进与防剧透
│   ├── rules/
│   │   ├── checks.py         # 检定：技能/对抗/幸运/理智
│   │   ├── combat.py         # 战斗、伤害、护甲、重伤、治疗
│   │   ├── insanity.py       # 疯狂状态机
│   │   ├── chase.py          # 追逐回合
│   │   └── retrieval.py      # 逐页 BM25 规则检索
│   └── agent/
│       ├── llm.py            #   OpenAI 兼容客户端
│       ├── tools.py          #   工具 schema + 规则引擎绑定
│       ├── memory.py         #   对话记忆（按回合裁剪）
│       ├── agent.py          #   工具调用循环
│       ├── prompts.py        #   系统提示词
│       ├── state.py          #   多人状态与 JSON 存档
│       ├── security.py       #   输入边界与注入防护
│       └── observability.py  #   tracing、token 与成本统计
└── tests/                    # 80 个单元/集成测试
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

# 1. （可选）从规则书 PDF 重新抽取文本
python scripts\extract_rules.py --toc          # 打印目录
python scripts\extract_rules.py --dump-all     # 抽取全文到 data/rulebook/

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

CLI 内可使用 `/status`、`/players`、`/trace`、`/save [路径]` 和 `/help`。
规则层、RAG、存档与离线评估不需要网络；在线 KP Agent 需要 `openai` 和兼容 API 密钥。

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
5. 在“模组库”中导入 PDF。模组保存在 `data/modules/`，完整内容只供 Keeper 侧使用。
6. 在“战役”中分别选择角色卡和模组后开局。战役保存在 `data/campaigns/`，角色状态变化会同步回永久角色卡。

角色卡、模组和战役是三个独立实体；删除或更换模组不会删除角色卡。

默认模型为 `deepseek-v4-flash`，并显式声明 `1,000,000` token 上下文窗口：

```dotenv
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_CONTEXT_WINDOW=1000000
```

应用不再设置“整个战役累计 token 上限”。供应商仍会限制单次请求的上下文长度，因此系统会永久保存
完整对话，只把近期完整工具回合和与当前输入相关的旧回合送入模型。这样可持续推进长战役，同时避免破坏
assistant/tool 消息配对。私有 PDF 内容会发送给所配置的模型供应商；使用第三方模型前应确认其数据政策。

## PDF 模组

运行中可用以下 Keeper 命令：

```text
/module add D:\Modules\scenario.pdf
/module status
/module next 玩家已找到钥匙并打开地下室
/module export data\modules\scenario-reviewed.json
```

导入器优先使用 PDF 目录切分场景；无目录时按最多 8 页切分，因此长短 PDF 都可处理。
扫描版 PDF 若没有文本层会明确提示先做 OCR。导入后会生成可编辑 JSON，建议在开跑前为每个场景补充
`objectives` 和 `secrets`：前者控制能否推进，后者加强对改写式剧透的输出拦截。

模组运行时只把当前场景送给 Agent，`search_module` 也只检索当前场景；未来场景按顺序锁定。
系统提示和最终输出门禁共同阻止完整剧情、未来秘密和结局泄露。`data/modules/*.json` 与 `saves/`
已被 Git 忽略，因为两者都包含 Keeper 私密内容，不应发给玩家。

---

## 里程碑状态

| # | 里程碑 | 内容 | 状态 |
| --- | --- | --- | --- |
| M0 | 规则引擎核心 | 骰子、角色卡、技能/对抗/幸运/理智检定 | 已完成 |
| M1 | 规则引擎扩展 | 战斗、射程、伤害/护甲、疯狂状态机、追逐、治疗 | 已完成 |
| M2 | 规则检索 RAG | 纯 Python BM25、逐页引用、内置核心规则回退 | 已完成 |
| M3 | KP Agent 核心 | 工具调用循环、记忆、规则查询、单人 CLI | 已完成；真实供应商需单独冒烟 |
| M4 | 多人跑团 | 多角色状态、团队幸运、JSON 存档与恢复 | 已完成 |
| M5 | 工程化 | 固定种子 eval、tracing、token/成本、输入安全、CLI | 已完成 |
| M6 | PDF 模组 | 目录/分页切分、当前场景检索、顺序推进、存档与防剧透 | 已完成 |
| M7 | 本地 WebUI | 永久角色卡、五组选卡、技能加点、模组库与独立战役 | 已完成 |
| M8 | 职业建卡 | Excel 职业目录、职业公式、双点池、信用评级与 70/60 上限 | 已完成 |

详细的学习路线见 [`docs/learning-plan.md`](docs/learning-plan.md)，按代码阅读的建议见
[`docs/learning-guide.md`](docs/learning-guide.md)，架构设计见 [`docs/design.md`](docs/design.md)。

在线验收边界：仓库不保存 API 密钥，也不把私有规则书全文提交到 Git。`scripts/smoke_llm.py`
和 `scripts/extract_rules.py` 分别用于在本机配置就绪后验证这两项外部资源。

---

## 规则依据

本项目规则严格依据《COC7th 核心规则书 v1.2.1》，所有判定均已对照规则书核实，
关键出处以注释形式写在对应模块的 docstring 中（如「表Ⅰ：伤害加值和体格表」、
「游戏系统摘要」p358 等）。规则的**正确性由单元测试锁定**，不依赖 LLM 记忆。
