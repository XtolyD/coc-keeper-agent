# 技能数据规范（Skill Catalog）

> 技能是 KP Agent 在跑团中最常用的知识。本文档定义技能事实、使用语义与 Agent 工具。

## 0. 分层

```text
skills_core.json      由 xlsx「附表」生成：名称、基础值、说明、难度、孤注一掷、失败示例
skills_playbook.json  人工维护：类别、使用场景、何时不用、易混淆技能、失败风格、触发词
SkillCatalog          合并两层数据，提供别名/父子/精确检索/行动候选
Agent tools           resolve_skill / search_skills / get_skill / roll_skill_check
```

原则：机制数值由数据/代码提供，叙事文本供检索；最终是否检定、用哪个技能由 KP Agent 判断。

## 1. 生成 skills_core.json

```powershell
python scripts\extract_skills.py
```

来源：`data/COC7空白卡.xlsx` 的 `附表!B95:K212`。

- 跳过空行、分隔行和“自定义技能”行。
- 保留来源 `source: {sheet, range}`。
- 基础值结构化：
  - `{"kind":"fixed","value":5}`
  - `{"kind":"attribute","attribute":"DEX","factor":0.5}`
  - `{"kind":"none"}`
- 子技能保留 `parent_name` 和 `canonical_name`：
  - 表演/美术/摄影等 → `艺术/手艺`
  - 手枪 → `射击（手枪）`
  - 斗殴/斧/剑等 → `格斗（斗殴）`
  - 数学/化学等 → `科学`
- 脚本不覆盖 `skills_playbook.json`。

## 2. skills_playbook.json

每个 canonical 技能至少包含：

```json
{
  "use_when": ["什么时候使用"],
  "avoid_when": ["什么时候应该换技能"],
  "alternatives": [{"skill": "替代技能", "difference": "区别"}],
  "check_type": "regular|opposed",
  "failure_style": "失败时如何付出代价/推进剧情",
  "triggers": ["用于把玩家行动匹配到技能的关键词"]
}
```

`triggers` 只用于给 Agent 提供候选；不是强制规则，最终由 Agent 选择。

## 3. SkillCatalog

```python
from coc_keeper.skills import get_skill_catalog

catalog = get_skill_catalog()
catalog.get("表演")                 # 子技能 → 艺术/手艺
catalog.canonicalize("取悦")        # 魅惑
catalog.search("开锁")              # 精确/别名优先，BM25 兜底
catalog.resolve_action("我搜查房间", character_skills)
```

- 精确名称/别名优先。
- BM25 只用于模糊检索；`triggers` 命中时不再拉入无关技能。
- `resolve_action` 返回候选、角色当前值、置信度、使用场景和替代技能，**不直接掷骰**。

## 4. Agent 工具

```text
resolve_skill(action, limit=3)       行动 → 候选技能（KP 决策参考）
search_skills(query, category, limit) 技能检索
get_skill(name, section=None)         单个技能完整说明
roll_skill_check(skill, difficulty)   执行检定；自动解析别名/子技能
```

`roll_skill_check` 找不到技能时返回 `{error, candidates}`，而不是直接失败。

## 5. 验收

- 110 条技能事实，55 个 canonical 技能。
- `SKILL_BASES` 与 `skills_core.json` 一致；闪避 = DEX/2，母语 = EDU。
- 55 个 canonical 都有 playbook。
- 典型行动：
  - 搜查房间 → 侦查
  - 偷听门后 → 聆听
  - 开锁 → 锁匠
  - 说服守卫 → 说服
  - 检查账本 → 会计
  - 表演戏剧 → 艺术/手艺（表演）
- 所有测试不联网。
