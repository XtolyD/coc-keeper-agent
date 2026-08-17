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
│   └── learning-plan.md      # 学习路线与里程碑
├── scripts/
│   ├── extract_rules.py      # 从规则书 PDF 抽取文本（供 RAG）
│   └── smoke_llm.py          # LLM 连通性 / 工具调用冒烟测试
├── data/
│   └── rulebook/             # 抽取出的规则全文（gitignored，可再生成）
├── src/coc_keeper/
│   ├── __init__.py
│   ├── config.py             # 配置：从 .env 读取模型与运行参数
│   ├── cli.py                # 交互式跑团入口（python -m coc_keeper.cli）
│   ├── dice.py               # 骰子机制：d100、奖励/惩罚骰、成功度、难度
│   ├── character.py          # 角色卡：属性、衍生属性、技能、建卡
│   ├── rules/
│   │   └── checks.py         # 检定：技能/对抗/幸运/理智
│   └── agent/                # KP Agent（M3）
│       ├── llm.py            #   OpenAI 兼容客户端
│       ├── tools.py          #   工具 schema + 规则引擎绑定
│       ├── memory.py         #   对话记忆（按回合裁剪）
│       ├── agent.py          #   工具调用循环
│       ├── prompts.py        #   系统提示词
│       └── state.py          #   会话状态
└── tests/                    # 30 个单元测试，规则引擎已全绿
```

---

## 环境搭建（Conda）

项目使用专用 Conda 环境 `coc-keeper`（Python 3.12.13，位于 `C:\Users\XtolyD\.conda\envs\coc-keeper`）：

```powershell
conda create -n coc-keeper python=3.12 pip -y
conda activate coc-keeper
pip install -r requirements.txt
```

## 快速开始

```powershell
conda activate coc-keeper
cd coc-keeper-agent

# 1. （可选）从规则书 PDF 重新抽取文本
python scripts\extract_rules.py --toc          # 打印目录
python scripts\extract_rules.py --dump-all     # 抽取全文到 data/rulebook/

# 2. 运行规则引擎测试
python -m pytest -q

# 3. （M3）交互式跑团：需先在 .env 配置 DEEPSEEK_API_KEY
python -m coc_keeper.cli
```

> 规则引擎核心零第三方运行时依赖；M3 Agent 需要 `openai`（已写入 requirements.txt）。

---

## 里程碑状态

| # | 里程碑 | 内容 | 状态 |
| --- | --- | --- | --- |
| M0 | 规则引擎核心 | 骰子、角色卡、技能/对抗/幸运/理智检定 | ✅ 已完成 |
| M1 | 规则引擎扩展 | 战斗、伤害、疯狂发作状态机、追逐 | ⏳ 待开始 |
| M2 | 规则检索 RAG | BM25 → 向量检索，让 Agent 能查规则 | ⏳ 待开始 |
| M3 | KP Agent 核心 | 工具调用循环（DeepSeek）、记忆、单人跑团 | 🚧 代码完成，待接入 DeepSeek 冒烟测试 |
| M4 | 多人跑团 | 多人会话、完整战役状态持久化 | ⏳ 待开始 |
| M5 | 工程化 | 评估、可观测性、成本与安全、CLI/界面 | ⏳ 待开始 |

详细的学习路线见 [`docs/learning-plan.md`](docs/learning-plan.md)，架构设计见 [`docs/design.md`](docs/design.md)。

---

## 规则依据

本项目规则严格依据《COC7th 核心规则书 v1.2.1》，所有判定均已对照规则书核实，
关键出处以注释形式写在对应模块的 docstring 中（如「表Ⅰ：伤害加值和体格表」、
「游戏系统摘要」p358 等）。规则的**正确性由单元测试锁定**，不依赖 LLM 记忆。
