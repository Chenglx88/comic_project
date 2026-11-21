---
name: episode-gate
description: 跑单集总门禁并逐项报告通过、未通过与需人工。当用户说「验收 EP01」「这集能不能过」「跑一下门禁」时使用。只读，不修文件。
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(python3 *)
argument-hint: <EPnn>
---

# Episode Gate

单集验收。用命令输出说话，只读不修。

## 1. 确认产物齐全

检查并列出：

- `02_script/episodes/EPnn_*.json`
- `03_storyboard/EPnn/{shots,dialogue,foley}.csv`
- `04_prompts/EPnn/S*.json`
- `06_render/EPnn/render_manifest.json`（L5 已跑时）

缺失项直接记为「未通过：缺失产物」，不跳过。

## 2. 跑门禁

```bash
python3 .claude/scripts/validate.py gate EPnn
python3 .claude/scripts/validate.py all
python3 .claude/hooks/selftest_hooks.py
```

## 3. 逐项报告

| 检查项 | 结果 | 依据 |
|:--|:--|:--|
| 剧本结构 | 通过 / 未通过 | `validate.py episode` |
| 分镜三表 | 通过 / 未通过 | `validate.py storyboard` |
| 提示词包 | 通过 / 未通过 | `validate.py prompts` |
| 镜头-提示词对应 | 通过 / 未通过 | `validate.py gate` |
| 角色锁一致性 | 通过 / 未通过 / 需人工 | hook 日志 + digest |
| 视觉一致性 | 需人工 | 需看图，本期无自动判据 |

## 4. 结论

- 全部通过 → `DONE`
- 有错误 → `BLOCKED`，列前 3 条错误与完整校验命令
- 有无法自动验证项 → `DONE_WITH_CONCERNS`，列未判项

判决用压缩判决 JSON，≤20 行 / 2KB。

## 禁止

- 不修改任何文件；发现问题只报告。
- 不跳过缺失产物；缺就是未通过。
- 不把「本轮不可判」记成通过。
- 不改 `00_schema/` 或校验器来让门禁变绿。
- 不在未跑完命令时给出结论。
