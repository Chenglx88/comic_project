---
name: episode-kickoff
description: 校验单集开工条件、建恢复点并输出派发清单。当用户说「开工第 X 集」「启动 EP01」「这集怎么开始」时使用。只写 .state/checkpoints/，不生产内容。
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - AskUserQuestion
  - Bash(python3 *)
argument-hint: <EPnn>
---

# Episode Kickoff

开工前的检查与派发清单。只准备，不生产。

## 1. 确认集号与专业

1. 从参数取 `EPnn`；缺参数就用 `AskUserQuestion` 问，不猜。
2. 读 `00_schema/majors.json`，核对 36 条专业中存在该集映射。
3. 读 `04_prompts/_shared/protagonist.json`，记录 `selected` 当前值。

## 2. 检查上游

按顺序检查，缺一项就记入 blockers，不跳过：

| 检查 | 路径 |
|:--|:--|
| 结构化数据 | `01_data/structured/<major_en>.json` |
| 导师画像 | `01_data/rankings/<major_en>.json` |
| 世界观 | `02_script/world_bible.md` |
| 角色圣经 | `02_script/character_bible.md` |
| 上一集剧本 | `02_script/episodes/EP(n-1)_*.json`（EP01 除外） |

## 3. 建恢复点

写 `.state/checkpoints/EPnn.json`：

```json
{
  "task_id": "EP01",
  "goal": "完成 EP01 剧本/分镜/提示词",
  "status": "in_progress",
  "stage": "L1",
  "completed_steps": [],
  "remaining_steps": ["L1", "L2", "L3", "L4", "L5", "L6"],
  "key_files": [],
  "last_command": "",
  "last_result": "",
  "blocked_by": [],
  "updated": "YYYY-MM-DDTHH:MM:SS"
}
```

同时更新 `.state/STATUS.md` 的对应行。

## 4. 输出派发清单

人读格式：

- 集号 / 专业 / 境 / 主角状态
- 上游缺失项（blockers）
- 建议顺序：`data-curator` → `scriptwriter` → `storyboard-director` → `prompt-engineer` → `render-orchestrate` → `continuity-auditor`
- 每步的验收命令

**只输出清单，不自动派发代理。**

## 禁止

- 不写剧本、分镜、提示词或任何 `01_data/`–`06_render/` 产物。
- 不自动派发子代理；派发由主会话决定。
- 不编造上游数据或把缺失项标为通过。
- 不在主角未定选时替用户选「烈」或「镜」。
