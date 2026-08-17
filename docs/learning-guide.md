# coc-keeper-agent 学习阅读指南

这份项目最适合按“确定性规则 → 检索 → Agent 协议 → 状态 → 工程化”的顺序阅读。
不要先从 `agent.py` 开始；如果不了解工具返回的数据从哪里来，很容易把 Agent 误解成一段提示词。

## 第一阶段：先掌握确定性核心

按以下顺序阅读：

1. `src/coc_keeper/dice.py`
2. `tests/test_dice.py`
3. `src/coc_keeper/character.py`
4. `src/coc_keeper/rules/checks.py`
5. `tests/test_character.py` 与 `tests/test_checks.py`

阅读时重点回答三个问题：随机性如何注入、规则边界如何表示、测试如何复现一次掷骰。
动手练习是为 `roll_dice` 增加一个非法输入用例，再预测失败发生在哪一层。

配套阅读：《Hands-On Large Language Models》中关于 token、生成模型能力边界与应用构建的章节。
这里不需要先学习 Transformer 数学细节。

## 第二阶段：理解状态机和战斗结算

依次阅读 `rules/combat.py`、`rules/insanity.py`、`rules/chase.py`，然后阅读
`scenarios.py` 和对应测试。重点观察“状态变化”没有交给 LLM，而是由数据类和纯函数负责。

建议练习：给食尸鬼增加 2 点护甲，固定随机种子运行 `run_ghoul_encounter`，解释为什么每轮结果可重放。
之后尝试为疯狂状态机增加治疗周期，但先写状态转换测试再改代码。

## 第三阶段：拆开 RAG

阅读 `rules/retrieval.py` 时按四段理解：分页切块、分词、文档频率、BM25 排序。
先运行以下查询并查看页码，再阅读 Agent 工具接入：

```powershell
python -c "from coc_keeper.rules.retrieval import load_default_index; print(load_default_index().search('奖励骰'))"
```

然后阅读《AI Engineering》的 RAG 章节。把 chunk、query、ranking、citation 四个概念与本项目中的
`RuleChunk`、`RuleIndex.search` 和 `search_rules` 工具逐一对应。向量检索应作为对比实验，而不是默认替代 BM25。

## 第四阶段：理解 PDF 模组的信息边界

先读 `modules.py`，再读 `tests/test_modules.py`。重点区分三种数据：完整 Keeper 模组、当前场景上下文、
玩家安全状态。观察为什么 `keeper_context` 从不搜索未来场景，以及 `advance` 如何用目标清单约束顺序。

建议练习：导入一个两页 PDF，在第二场景的 `secrets` 中加入一个真相，验证第一场景既搜不到它，
Agent 也不能把它直接发给玩家。随后修改 `objectives`，观察未完成目标时推进为何失败。

## 第五阶段：理解工具调用协议

阅读顺序：

1. `agent/llm.py`：供应商响应如何归一化成 `LLMResponse`。
2. `agent/memory.py`：assistant tool call 与 tool result 为什么不能被拆开。
3. `agent/tools.py`：JSON schema 如何映射到确定性函数。
4. `agent/agent.py`：循环终止条件、工具结果回填与单次调用边界。
5. `tests/test_agent.py`：不用真实模型也能验证协议。

配套阅读《AI Engineering》的 Agent 章节，以及 Anthropic 的 *Building Effective Agents*。
读完后应能在纸上画出 user → assistant/tool call → tool result → assistant 的完整消息序列。

## 第六阶段：多人状态和持久化

阅读 `agent/state.py`，重点看 `Session.to_dict/from_dict` 与 `CampaignStore`。这里要区分短期对话记忆和
长期业务状态：前者可以裁剪，后者必须保存。建议先手工生成两名调查员的存档，再删除内存对象并从 JSON 恢复。

进一步练习：为战役日志增加游戏内时间字段，并写一个旧版本存档迁移测试。不要直接上数据库；先把 JSON 模型边界做稳。

接着阅读 `character_store.py`、`module_store.py` 和 `game_store.py`。重点理解角色卡、模组、战役为什么使用
独立 ID：角色卡是玩家长期资产，模组是 Keeper 内容，战役只引用两者并保存当局进度。随后观察完整 transcript
如何永久保存，而送入模型的近期记忆和相关旧回合如何受单次上下文窗口约束。

建议练习：用同一张永久角色卡创建两个不同模组的战役，分别修改 HP，再解释当前“同步回角色卡”策略的覆盖语义。
这是继续设计角色版本、战役分支或并发锁之前必须回答的问题。

## 第七阶段：阅读 WebUI 边界

先读 `web.py` 的请求模型和路由，再读 `web_static/app.js`。不要从 CSS 开始。把每个页面操作对应到存储层：
五组属性生成是临时草稿，技能加点通过服务端重新校验，永久保存才会创建角色 ID；开战役时角色与模组分别选择。

建议练习：先在 `tests/test_web.py` 增加一个超预算技能分配用例，再尝试绕过前端直接调用 API，确认服务端仍拒绝。
这能直观看出“前端约束改善体验，后端约束保证正确性”的区别。

## 第八阶段：工程化闭环

依次阅读 `agent/security.py`、`agent/observability.py`、`evaluation.py` 和 `scripts/run_evals.py`。
分别对应输入边界、运行证据、质量门禁和自动化入口。

配套阅读：

- 《Designing Machine Learning Systems》中评估、监控和数据分布变化相关章节。
- OWASP LLM Top 10 中 prompt injection、敏感信息泄露和过度代理权限条目。
- 所用供应商的 function calling 与 token usage 官方文档。

不要只看总分。硬规则指标必须全部通过；叙事 rubric 用于比较版本，不应替代人工跑团体验。

## 推荐的两周节奏

| 天数 | 内容 | 验收产物 |
| --- | --- | --- |
| 1–2 | 骰子、角色卡、检定 | 能解释并新增一个边界测试 |
| 3–4 | 战斗、疯狂、追逐 | 修改固定场景且结果可复现 |
| 5–6 | BM25 规则检索 | 三个查询均返回正确页码 |
| 7–8 | PDF 模组与信息隔离 | 当前场景无法读取未来秘密 |
| 9–10 | LLM 消息与工具循环 | 手写一份完整消息序列 |
| 11 | 多人状态与独立存储 | 两人战役保存并恢复，解释三个存储 ID |
| 12 | WebUI 与 API | 绕过前端后服务端仍拒绝非法技能点 |
| 13 | 安全、追踪、评估 | 解释一次 trace 和一次拦截 |
| 14 | 真实模型冒烟 | 完成短场景并复盘工具调用与旧回合检索 |

每天先读 30–45 分钟，再用 60–90 分钟改测试或代码。项目的核心学习目标不是“让模型说得像 KP”，
而是能证明每个规则结果、状态变化和工具调用为什么正确。
