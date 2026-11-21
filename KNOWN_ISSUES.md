# KNOWN_ISSUES

已知问题事实源。现象、影响、触发条件、临时规避、状态、登记日期缺一不可。TODO 只在决定修复时登记指针，不重述现象。

| 编号 | 现象 | 影响 | 触发条件 | 临时规避 | 状态 | 登记日期 |
|:--|:--|:--|:--|:--|:--|:--|
| P-01 | 方案 §6 命名示例与 §4 的 `<major_en>` 写法不完全一致 | 产物文件名可能各写各的 | 人工按方案示例创建产物 | 以 `00_schema/storyboard_headers.json` 与 `guard_paths.py` 正则为准 | 开放 | 2026-11-21 |
| P-02 | 方案 §4.6 写 `character_sheet.md`，实际落地为 `character_lock.json` | 按旧文档找不到锁文件 | 阅读方案后直接找 `character_sheet.md` | 以 `04_prompts/_shared/character_lock.json` 为唯一事实源 | 已规避 | 2026-11-21 |
| P-03 | 仓库 `git init` 后无任何提交 | 无历史可回滚，误删无法恢复 | 执行破坏性操作前 | 重大改动前先 `git add -A && git commit`（需用户确认） | 开放 | 2026-11-21 |
| P-04 | PostToolUse 在文件落盘后才执行，无法撤销坏写入 | 校验失败的文件已存在 | 写入不合规产物 | hook 回灌前 3 条错误；随后人工或代理修正并重跑 `validate.py` | 开放（平台限制） | 2026-11-21 |
| P-05 | 方案附录 A 的模型名、上下文窗口、价格为 2026 公开信息 | 按旧信息选型会产出漂移或超预算 | 直接照抄方案模型 ID | 运行时查厂商最新模型卡并 pin 明确 ID | 开放 | 2026-11-21 |
| P-06 | `07_pipeline/` 无代码 | L1-L6 只能手工执行，无法批量与复现 | 需要跑产品流水线 | 先用代理按层手工生产 EP01 | 开放 | 2026-11-21 |
| P-07 | 主角未定选，`protagonist.json` 为 `undecided` | 角色锁前缀与 seed 校验处于弱模式 | 生成提示词 | 提示词保持 `undecided`+`sha256:pending`；定选后重跑 | 开放 | 2026-11-21 |
| P-08 | Edit 的 `old_string` 不在磁盘内容中时，hook 无法重建前瞻内容 | 该次 Edit 的角色锁校验被跳过 | 并发修改或 `old_string` 写错 | 写入后跑 `validate.py prompts` 兜底；hook 记 allow 日志 | 开放（fail-open） | 2026-11-21 |
| P-09 | `pytest` / `ruff` / `mypy` 未安装 | 代码质量门禁无法执行 | 运行对应命令 | 日一用 `compileall` + `validate.py` + selftest；安装后再启用 | 开放 | 2026-11-21 |
| P-10 | `.state/` 被 `.gitignore` 忽略 | 进度与恢复点不进入版本历史 | 换机器或清工作区 | 需要迁移时手动打包 `.state/` | 已接受 | 2026-11-21 |
