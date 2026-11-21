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

## 未闭合缺口

| 编号 | 缺口 | 影响 |
|:--|:--|:--|
| G-01 | 无 `07_pipeline/` 代码 | 产品 L1-L6 目前只有模板，无法运行 |
| G-02 | git 仓库无任何提交 | 无法回滚与对拍 |
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
| D-08 | 关键帧/视频工具组合 | 待定，按方案 §5 清单 |
| D-09 | 是否创建首个 git 提交 | 待定，当前只 init |
| D-10 | 资产版本管理是否上 LFS | 待定，暂用 Git + 目录版本号 |
