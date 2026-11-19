# 项目 OOP 与功能检查

日期：2026-10-26。检查基线：`main`，提交 `d25acfd`。以下问题清单描述修复前的复现结果，代码引用按检查基线定位。

**修复状态**：F01—F05、F08—F13 已修复并补充回归测试；当前实现与开发主线统一为一名玩家操控一名调查员、AI 担任 KP。全量 Python 测试 204 项通过，前端请求去重回归 3 项通过。实现与验收边界见 [CHANGELOG.md](D:/WorkStation/COC/CHANGELOG.md)。

**结论：项目采用局部 OOP 与纯函数混合的架构，符合自身设计方向；已确认存在现有测试未覆盖的功能缺陷。无需为了 OOP 将规则计算全面改写成类，应优先修复规则结果、状态一致性和模组运行边界。**

## OOP 设计判断

| 检查维度 | 当前实现与判断 |
| --- | --- |
| 职责划分 | `KeeperAgent`、`ModuleApplicationService`、`ModuleImportPipeline`、各 Store、`JobManager` 分别承担编排、用例、流程、持久化和后台任务；方向合理。 |
| 接口与可替换性 | `module_pipeline/ports.py` 的三个 `Protocol` 隔离解析、复核和分析，流水线接受构造注入；已实际使用接口多态。 |
| 组合复用 | 角色、模组、战役 Store 组合 `JsonRecordRepository[T]`，比建立复杂继承树更符合当前规模。 |
| 规则计算 | 骰子、检定、BM25 等使用纯函数，领域数据使用 dataclass，符合 `docs/design.md` 第 4.1 节。纯函数数量不构成 OOP 不合格的证据。 |
| 封装不足 | 工具闭包直接写角色字段，角色集合、主角色、疯狂状态之间的约束没有集中维护，已导致下面的角色生命周期缺陷。 |
| 依赖注入不完整 | Agent 和应用服务内部仍直接构造配置及客户端；`create_app()` 依赖共享全局应用。测试可替换性和实例隔离还有改善空间。 |
| 应用服务边界 | Web 路由同时执行回合、保存战役并同步角色，缺少跨记录保存的一致性与失败恢复策略。 |

## 已验证的功能问题

P1 表示建议优先修复，会改变核心判定、剧情或持久状态；P2 表示明确功能缺陷，触发范围较窄或主要影响展示、容错与扩展场景。

### F01 · P1 · 个位为零时奖惩骰选择方向错误

位置：[dice.py:144](D:/WorkStation/COC/src/coc_keeper/dice.py:144)。`d100()` 先对原始十位数字取 min/max，之后才将 00 转成 100，导致百分骰完整数值的顺序改变。

复现：个位为 0，两个十位为 0 和 5，完整候选值是 100 与 50。奖励骰实际返回 100，应为 50；惩罚骰实际返回 50，应为 100。该问题会直接改变技能检定、对抗和相关战斗结果。

规则依据：[Chaosium 官方规则](https://cthulhuwiki.chaosium.com/rules/game-system.html#bonus-and-penalty-dice)：00 与 0 组成 100；奖励骰选择更低的最终结果，惩罚骰选择更高的最终结果。建议先构造每个完整百分骰结果，再选择最优或最差值。

### F02 · P1 · 新战役忽略剧情图声明的入口

位置：[modules.py:474](D:/WorkStation/COC/src/coc_keeper/modules.py:474)。新建 `ModuleRuntime(module)` 时默认选 `story.nodes[0]`，没有选 `story.entry_node_id`。

复现：合法图的入口为 `n-entry`，节点顺序为 `[n-ending, n-entry]`，实际从 `n-ending` 开局。Web 创建战役使用该默认构造路径；界面也允许单独编辑入口节点。

建议新战役明确使用入口节点，旧存档的索引兼容仅用于恢复流程。

### F03 · P1 · 同页未来原文被混入当前场景上下文

位置：[module_analysis.py:293](D:/WorkStation/COC/src/coc_keeper/module_analysis.py:293)。`_build_module()` 按页码相交重新生成 `source_chunk_ids`，覆盖已提供的精确引用。

复现：同一页有当前块 `c-current` 和未来块 `c-future`；当前场景显式只引用前者。构建后变成同时引用两个块，`keeper_context()['excerpts']` 已包含未来秘密。

这确认了“未来原文不会进入当前上下文”的边界失效；本次没有调用真实 LLM，不能据此声称最终玩家回复必然泄露秘密。建议保留有效精确引用，只有引用缺失时才考虑受限回退。

### F04 · P1 · 旧战役快照覆盖永久角色最新状态

位置：[web.py:451](D:/WorkStation/COC/src/coc_keeper/web.py:451)、[web.py:498](D:/WorkStation/COC/src/coc_keeper/web.py:498)。创建战役复制角色卡，每次对话又将整张战役内角色卡写回永久角色，没有版本冲突检查。

复现：HP10 的同一角色建立 A/B 两个战役。A 受伤后永久 HP7；B 只执行无伤害的观察行动，永久 HP 回到 10。无需并发即可触发。

建议明确永久角色与战役角色的同步语义，采用版本检查、字段变更合并，或限制同一角色的同时活动战役，避免静默覆盖。

### F05 · P2 · 技能页默认“全部”返回空列表

位置：[app.js:595](D:/WorkStation/COC/src/coc_keeper/web_static/app.js:595)、[web.py:288](D:/WorkStation/COC/src/coc_keeper/web.py:288)。前端发送 `category=`，后端只将 `None` 视作全部，将空字符串作为真实类别过滤。

使用真实 FastAPI TestClient 验证：`/api/skills?limit=80` 返回 80 条；`/api/skills?q=&category=&limit=80` 返回 0 条；选择“全部”时搜索“侦查”也返回 0 条。现有 API 测试没有模拟这个实际前端参数。

建议统一空类别的语义，服务端将空白规范化为 None，或前端省略未选类别。

### F08 · P2 · 新角色继承旧角色的疯狂状态

位置：[tools.py:84](D:/WorkStation/COC/src/coc_keeper/agent/tools.py:84)、[state.py:25](D:/WorkStation/COC/src/coc_keeper/agent/state.py:25)、[tools.py:177](D:/WorkStation/COC/src/coc_keeper/agent/tools.py:177)。重建单人角色只替换角色卡，未替换会话中的疯狂追踪器。

复现：旧角色 SAN0、permanent；新建 New 后 SAN60，再做零理智损失检定，仍返回 permanent。

建议将疯狂追踪归属角色，或在明确替换角色时正确重置关联状态。

### F09 · P2 · 工具参数错误仍部分扣除角色数值

位置：[tools.py:186](D:/WorkStation/COC/src/coc_keeper/agent/tools.py:186)。`update_character()` 转换一个参数就立即写一个字段，后续参数转换失败不会回滚。

复现：HP10，调用 `delta_hp=-3, delta_mp='bad'`，工具返回 ValueError，但 HP 已变7；纠正参数后重试会再次扣血。`bad` 不符合工具 schema，这是一项对畸形模型参数的失败处理缺陷；dispatcher 当前并未执行 schema 校验。

建议先完整验证并计算所有新值，再一次性应用修改。

### F10 · P2 · 回合保存部分成功后仍向客户端报错

位置：[web.py:497](D:/WorkStation/COC/src/coc_keeper/web.py:497)、[app.js:721](D:/WorkStation/COC/src/coc_keeper/web_static/app.js:721)。先保存战役，再保存永久角色，第二次保存失败时第一步已经提交。

故障注入复现：令 `characters.save` 抛 OSError，请求失败，但战役已增加两条持久对话并扣除 HP，永久角色未同步。前端恢复输入供重试时，玩家可能再次执行已经落盘的行动。

建议协调提交与失败恢复，并为回合提供可识别的请求 ID 或其他幂等保障。

### F11 · P2 · 困难检定失败仍在摘要显示“常规成功”

位置：[agent.py:69](D:/WorkStation/COC/src/coc_keeper/agent/agent.py:69)、[tools.py:110](D:/WorkStation/COC/src/coc_keeper/agent/tools.py:110)。工具分别返回自然成功度和是否达到要求难度，玩家摘要只显示前者。

复现：技能60、困难目标30、骰值40，工具 `成功=False`，摘要却为 `D100=40 / 目标=30 · 常规成功`。底层布尔判定正确，但玩家展示与行动是否成功相冲突。

建议摘要明确区分“本次行动成败”与“自然成功度”。

### F12 · P2 · 场景语义校验失败时批次回退失效

位置：[module_analysis.py:119](D:/WorkStation/COC/src/coc_keeper/module_analysis.py:119)、[module_analysis.py:157](D:/WorkStation/COC/src/coc_keeper/module_analysis.py:157)。批次 try/except 只覆盖请求和 JSON 解析，领域校验稍后集中执行；失败后仅清空故事图，无法修复非法场景。

离线模型 stub 返回可解析 JSON，但场景 `page_start=9, page_end=1`。`analyze()` 最终抛 ValueError，没有将该批次回退为原文场景并返回 partial，整项导入失败。

建议每个场景批次完成后立即做结构与领域校验，失败批次使用已有回退函数。

### F13 · P2 · 应用工厂不能隔离两个应用实例

位置：[web.py:157](D:/WorkStation/COC/src/coc_keeper/web.py:157)。`create_app()` 修改全局 `app.state.context` 并返回同一个应用对象。

复现：分别以 A/B 数据目录创建应用，得到 `app_a is app_b == True`，第二次创建后 `app_a` 的上下文也被改为 B。单实例默认运行不因此失败，但测试隔离或同进程多应用会使用错误的数据上下文。

建议工厂真正创建应用，并通过该应用或 request 绑定上下文。

## 验证与限制

- 使用 `C:\Users\XtolyD\.conda\envs\coc-keeper\python.exe`，Python 3.12.13；确认导入当前工作区源码。
- 在解除沙盒临时目录与 Windows 本地 socket 限制后，原有测试 **159/159 通过，2.59秒**。上一轮沙盒内 PermissionError 和 TestClient 阻塞不能直接视为应用缺陷。
- 上述缺陷由额外固定输入、离线路由调用、真实本地 TestClient 请求或明确故障注入复现。正常流程问题与异常参数/存储故障触发的问题分别说明。
- 复现脚本位于 `.pytest_cache/repro_agent_review.py`、`.pytest_cache/web-review/repro.py`、`.pytest_cache/module_review_repro.py`；使用隔离目录、stub 或 mock，不调用真实模型和 MinerU。
- 未验收真实 PDF 导入、在线模型表现、完整叙事质量，也未宣称完成 CoC 全部规则逐条审计。当前本地规则书语料缺失属于部署数据未就绪，与以上代码缺陷分开处理。
- README 的常见行动自动检定描述与当前代码不一致；当前由 Agent 自主决定调用工具，现有测试明确要求没有工具调用就不自动掷骰。这项按文档漂移处理，不擅自认定应恢复自动判定。
- DeepSeek 外部复审请求被自动审批拒绝，理由为项目文档和源码的外部披露风险；已改为本地子代理审查，报告结论经主 Agent 复核。

修复后的主要约束：新战役使用声明入口；精确原文块引用保留；语义无效批次回退；回合从永久角色读取最新数值；提交通过写前日志协调并保存请求编号。真实模型与 PDF 在线验收仍需另行进行。
