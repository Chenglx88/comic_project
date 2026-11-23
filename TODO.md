# TODO

不含进度；进度只写 `.state/`。

## 待办

| 编号 | 事项 | 验收 |
|:--|:--|:--|
| T-01 | 实现 `07_pipeline/` 六层流水线代码 | 可按 L1→L6 串跑单集，pytest/ruff/mypy 通过 |
| T-02 | EP01 双主角 A/B 试播后定选 | `protagonist.json` 的 `selected` 不再为 `undecided` |
| T-03 | 补两角色 RGB 色值与 seed 区间 | `character_lock.json` 通过 schema 且 hook 前缀/seed 校验生效 |
| T-04 | 生产 EP01 三件套：剧本、分镜、提示词 | `validate.py gate EP01` 通过 |
| T-05 | pipeline 落地后补 `meta.sh` 与 T2 三腿账本 | 元任务可建、可恢复、可归档判决 |
| T-06 | 补 `pytest` / `ruff` / `mypy` 并接入门禁 | `CLAUDE.md §3` 的「待生效」改为「已生效」 |
| T-07 | 审核 L1 数据（G3-DATA） | 课程/就业来源可核验，用户批准；弱来源改由用户决定是否重跑 |

## 未闭合缺口

| 编号 | 缺口 | 影响 |
|:--|:--|:--|
| G-01 | 无 `07_pipeline/` 代码 | 产品 L1-L6 目前只有模板，无法运行 |
| G-03 | 无角色资产库与参考图 | 角色锁的 `reference_images` 为空，图生图无法启动 |
| G-04 | 无真实专业数据 | `01_data/` 为空，EP01 剧本只能写占位内容 |

## 决策登记

| 编号 | 决策 | 状态 |
|:--|:--|:--|
| D-01 | 本期不做 `meta.sh`、worktree、CI | 已定 |
| D-02 | L5 渲染编排做成 skill，不设代理 | 已定 |
| D-03 | `continuity-auditor` 只读，不写产物 | 已定 |
| D-04 | 产品 LLM 路由与 Claude Code 子代理路由严格分离 | 已定 |
| D-05 | 主角定选 | 待定，当前 `undecided` |
| D-06 | 两角色 RGB 与 seed 区间 | 待定，当前 `null` / `pending` |
| D-07 | 提示词主语言 | 待定，暂按中文为主 + 英文标签 |
| D-08 | 关键帧/视频/配音组合：即梦/Seedream + 可灵 + 火山 TTS | 已定（2026-11-22） |
| D-09 | 创建首个 git 提交并推送 `origin/main` | 已定（2026-11-21） |
| D-10 | 资产版本管理是否上 LFS | 待定，暂用 Git + 目录版本号 |
| D-11 | 图像 provider 由 NovelAI 改为即梦/Seedream（火山方舟） | 已定（2026-11-22，用户要求国内 provider） |
| D-12 | L1 从旧 CAM 混元迁到 TokenHub；模型由 `hy4` 改为 `deepseek-v4.1-flash-1017`（hy4 与搜索注入不兼容，见 P-19） | 已定（2026-11-22，用户批准换 DeepSeek） |
| D-13 | 实际模型 pin：L1 `deepseek-v4.1-flash-1017`；L2 `qwen3.6-plus-2026-04-02`；L3 `deepseek-flash`；L4/L5 `glm-5.3`；Kling `kling-3.0`；Seedream `doubao-seedream-5-5-261028`；TTS `seed-tts-2.0` | 已定（2026-11-22；L1 已产出待审核） |
