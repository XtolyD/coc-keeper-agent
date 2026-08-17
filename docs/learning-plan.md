# 学习路线与里程碑

> 把「Agent 构建工程」的学习，落进 coc-keeper-agent 这个真实项目里。
> 原则：**读书:动手 = 3:7**，每个里程碑都要交付「能跑、能测、能验收」的东西。

## 里程碑总览

| # | 里程碑 | 学什么 | 交付物 | 对应书籍/资源 |
| --- | --- | --- | --- | --- |
| M0 | 规则引擎核心 | 纯函数设计、可注入随机数、单元测试 | `dice/character/checks` + 30 测试 | 《Hands-On LLMs》前半 |
| M1 | 规则引擎扩展 | 状态机（疯狂）、战斗结算 | 战斗/伤害/疯狂状态机 | — |
| M2 | RAG 规则检索 | 检索原理、分块、BM25→向量 | 规则查询工具 | 《AI Engineering》RAG 章 |
| M3 | KP Agent 核心 | 工具调用循环、结构化输出、记忆 | 单人跑团 CLI | 《AI Engineering》Agent 章 |
| M4 | 多人跑团 | 多会话状态、持久化、团队检定 | 多人跑团 | Anthropic《Building Effective Agents》 |
| M5 | 工程化 | 评估、可观测性、成本/安全 | eval 套件 + tracing | 《Designing ML Systems》 |

---

## M0 · 规则引擎核心 ✅（本轮已完成）

**学习目标**
- 把"规则"建模为**纯函数 + 数据类**，所有随机性通过可注入 `rng` 传入——这是
  Agent 工具可靠性的第一课：**确定性部分必须可测试、可复现**。
- 用单元测试锁定规则正确性（大失败/奖励骰/理智阈值等边界）。

**交付物**：`src/coc_keeper/dice.py`、`character.py`、`rules/checks.py`，30 个测试全绿。

**验收标准**：`python -m pytest -q` 全绿；每个判定都能追溯到规则书页码。

---

## M1 · 规则引擎扩展

**学习目标**：状态机建模（CoC 的疯狂发作是一个经典状态机：临时→潜在→恢复）。

**交付物**
- 战斗：战斗轮、近战（对抗格斗）、射击（难度/射程修正）、伤害与护甲、重伤。
- 疯狂：疯狂发作（即时/总结症状）、临时/不定/永久疯狂状态流转。
- （可选）追逐规则。

**验收标准**：能跑通一场"遭遇食尸鬼→理智检定→疯狂发作→战斗→治疗"的纯规则模拟。

---

## M2 · RAG 规则检索

**学习目标**：检索的本质——分块、倒排索引、相关性排序；理解 BM25 与语义检索的取舍。

**交付物**
- 规则书分块（按页，页号即出处，便于"引用规则"）。
- `search_rules(query)` 工具：BM25 版先行；对比实验向量版。

**验收标准**：对"奖励骰怎么掷""临时性疯狂的判定"等查询，能命中正确规则段落并带页号。

**关键阅读**：《AI Engineering》RAG 章节；langchain/llamaindex 的检索概念文档。

---

## M3 · KP Agent 核心（本项目重头戏）

**学习目标**
- 工具调用（function calling）循环：消息如何拼接、工具结果如何回填、如何封顶循环。
- 结构化输出：让 LLM 产出可解析的工具参数与判定。
- 记忆与状态：对话历史裁剪/摘要 + 结构化角色卡。
- 系统提示设计：把"规则纪律 + 角色扮演"写进 prompt。

**交付物**
- `src/coc_keeper/agent/`：手写 tool-calling 循环（DeepSeek，OpenAI 兼容）。
- 工具集：检定/对抗/幸运/理智/角色卡读写/规则查询。
- 单人跑团 CLI：能完整主持一个短场景。

**验收标准**：与 AI KP 完整跑一段剧情，所有骰子/理智/HP 变化均由工具结算且正确；
Agent 不会卡死、不会无限循环、不会胡编规则。

**关键阅读**：《AI Engineering》Agent 章；Anthropic《Building Effective Agents》；
DeepSeek/OpenAI 的 function calling 文档。

---

## M4 · 多人跑团

**学习目标**：多主体状态管理、行动顺序、团队检定（团队幸运检定等）、持久化。

**交付物**：多人会话管理、战役存档（JSON）、团队检定工具。

**验收标准**：2+ 玩家能同时跑团，各自角色卡独立结算，存档可恢复。

**关键阅读**：Anthropic《Building Effective Agents》中"多 Agent 编排"的克制建议——
**优先用单 Agent + 好的状态/工具解决，而不是无脑上多 Agent**。

---

## M5 · 工程化

**学习目标**：把"玩具 Demo"变成"可靠系统"。

**交付物**
- **评估**：固定模组（《古茂密林之中》）+ 固定随机种子；硬指标（规则正确）用
  规则引擎校验，软指标（叙事/氛围）用 LLM judge + rubric。
- **可观测性**：tracing（每次工具调用入参/出参、token 用量、延迟）。
- **成本与安全**：token 预算、prompt injection 防护（玩家输入不能劫持 KP 的规则纪律）。
- **界面**：CLI 美化或 Web UI。

**验收标准**：一套 eval 能自动跑并输出分数；一次跑团的成本/延迟可观测；
恶意玩家输入不会让 KP 违反规则。

**关键阅读**：《Designing Machine Learning Systems》（评估/监控/部署的思维）；
OWASP LLM Top 10（安全）。

---

## 参考书单（精简版）

| 优先级 | 书名 | 在哪个里程碑用 |
| --- | --- | --- |
| ⭐⭐⭐ | 《AI Engineering》Chip Huyen（2025） | M2-M5 主线 |
| ⭐⭐⭐ | 《Hands-On Large Language Models》 | M0-M3 建立直觉 |
| ⭐⭐ | 《Build a LLM From Scratch》 | 背景内功，有余力再啃 |
| ⭐⭐ | 《Designing Machine Learning Systems》 | M5 工程纪律 |
| 📄 | Anthropic《Building Effective Agents》 | M3/M4 必读 |

规则书：《COC7th 核心规则书 v1.2.1》（已抽取到 `data/rulebook/`）。
