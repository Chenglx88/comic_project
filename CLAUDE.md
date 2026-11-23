# CLAUDE.md — 《五境试炼》

## §1 一句话与入口

《五境试炼》：3 分钟 2D 动漫 × 大学专业科普，36 集首批，交付成片 MP4。

| 入口 | 用途 |
|:--|:--|
| [README.md](README.md) | 项目结构、环境、启动、外部工具 |
| [TODO.md](TODO.md) | 待办、未闭合缺口、决策登记 |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | 已知问题事实源 |
| `.state/` | 在飞任务进度与恢复点（唯一权威源） |
| `comic_project_plan.md` | 内容设定与业务方案权威源 |
| `00_schema/` | 机器可读契约（专业表、剧本、分镜、提示词、角色锁） |
| `04_prompts/_shared/` | 主角选择与角色锁 |
| `07_pipeline/` | 产品流水线代码（待建） |

## §2 模块依赖与现状异常

**依赖链**：L1 `data-curator` → `01_data` → L2 `scriptwriter` → `02_script/episodes` → L3 `storyboard-director` → `03_storyboard` → L4 `prompt-engineer` → `04_prompts` → L5 `render-orchestrate` skill → `06_render` → L6 `continuity-auditor`。

**契约**：每层只读上游、只写本层目录。`00_schema/` 被 hooks、`validate.py`、全部代理共同消费；`04_prompts/_shared/character_lock.json` 被 L4/L5 消费；`04_prompts/_shared/protagonist.json` 是主角选择的唯一权威。

目录树见 [README.md §1](README.md)。

### 与指引不符的致命事实

| 说法 | 实际 | 重验命令 |
|:--|:--|:--|
| 方案 §4 的 L1-L6 是产品运行时路由，调用国产模型 API | 不是 Claude Code 子代理路由；两套系统互不替代 | `grep -n '^### 4.3' comic_project_plan.md` |
| 方案 §6 的目录已存在 | 由本次配置建立；以 README §1 为准 | `find . -maxdepth 1 -type d \| sort` |
| 方案 §4.6 写 `character_sheet.md` | 实际为 `04_prompts/_shared/character_lock.json` | `ls 04_prompts/_shared/` |
| 方案附录 A 的模型名与价格为 2026 公开信息 | 可能过期；运行时必须 pin 明确模型 ID | `grep -n '2026' comic_project_plan.md` |
| 方案 §4.3 写 L1 用腾讯混元旧 CAM API | 旧模型已下线；实际用 TokenHub `hy4` + `web_search_options` | `grep -n 'TokenHub' 07_pipeline/config/env.example` |
| 3 分钟是 1 次生成 | 实际为 40-60 个镜头拼接 | `grep -n '40~60' comic_project_plan.md` |
| 主角已定 | `protagonist.json` 默认 `undecided` | `cat 04_prompts/_shared/protagonist.json` |

## §3 调度规则

**技术栈**：Python 3.12.3；hooks 与校验器仅用标准库。`pytest` / `ruff` / `mypy` 未安装，列为「待生效门禁」，未安装前不得声称通过。

### 已生效门禁

| 槽位 | 命令 |
|:--|:--|
| 全部产物 | `python3 .claude/scripts/validate.py all` |
| 单集剧本 | `python3 .claude/scripts/validate.py episode <path>` |
| 分镜三表 | `python3 .claude/scripts/validate.py storyboard 03_storyboard/EP01` |
| 单张分镜 | `python3 .claude/scripts/validate.py storyboard-file <path>` |
| 提示词包 | `python3 .claude/scripts/validate.py prompts 04_prompts/EP01` |
| 单集总门禁 | `python3 .claude/scripts/validate.py gate EP01` |
| Schema 自检 | `python3 .claude/scripts/validate.py schema` |
| 角色锁自检 | `python3 .claude/scripts/validate.py lock` |
| 文档一致性 | `python3 .claude/scripts/validate.py docs` |
| Hook 自检 | `python3 .claude/hooks/selftest_hooks.py` |
| 语法检查 | `python3 -m compileall -q .claude 07_pipeline` |

### 待生效门禁（`07_pipeline` 落地并安装依赖后启用）

`pytest -x`、`ruff check .`、`mypy 07_pipeline`。缺工具时记 `SKIP`，不得记 `pass`。

### 表 A：产品 LLM 路由（运行时，非子代理）

层级、主选模型、触发条件以方案 §4.3 为准；此处只固定职责边界。模型别名不得直接使用，必须 pin 明确 ID。

| 层 | 职责 | 输入 → 输出 |
|:--|:--|:--|
| L1 数据层 | 联网检索并结构化专业数据 | 专业名/URL/年份 → `01_data/**` |
| L2 剧本层 | 3 分钟剧本与世界观状态 | 数据 + 圣经 → `02_script/episodes/EPnn_*.json` |
| L3 分镜层 | 拆镜头、构图、运镜、台词 | 剧本 → `03_storyboard/EPnn/*.csv` |
| L4 提示词层 | 单镜图/视频提示词包 | 分镜 + 角色锁 → `04_prompts/EPnn/S###.json` |
| L5 渲染编排 | 调度外部图/视频/音频工具 | 提示词包 → `06_render/` |
| L6 质检层 | 术语、一致性、时长、视觉抽检 | 全部产物 → 判决与回流项 |

### 表 B：Claude Code 子代理路由（开发期）

| 任务类型 | 代理 | 输入 | 输出 |
|:--|:--|:--|:--|
| 专业数据采集 | `data-curator` | 专业、URL、年份 | `01_data/structured/` |
| 单集剧本 | `scriptwriter` | 数据、圣经、主角配置 | `02_script/episodes/` |
| 分镜三表 | `storyboard-director` | 单集剧本 JSON | `03_storyboard/EPnn/` |
| 镜头提示词 | `prompt-engineer` | 分镜、角色锁、模板 | `04_prompts/EPnn/` |
| 文本一致性审计 | `continuity-auditor` | 全部产物 | 压缩判决（只读） |
| 流水线编码 | `pipeline-coder` | SPEC | `07_pipeline/` |
| 流水线复审 | `pipeline-reviewer` | diff、SPEC | 压缩判决（只读） |
| 流水线验收 | `pipeline-tester` | 验收标准 | 压缩判决 |

**生产顺序**：L1 → L2 → L3 → L4 → L5 → L6。上游 schema 不过，不得进入下游。

**分支**：每集 `ep/EPnn`；单集串行，本期不开 worktree。

**中断**：进度只写 `.state/checkpoints/EPnn.json`；恢复时先读该文件与 `.state/STATUS.md`。

**档位**：T0 单镜/单句修正；T1 单集生产（默认）；T2 跨集重构/管线改造。本期 T2 只留条文规范，不建 router。

## §4 子代理派发

| 代理 | 触发 | 写面 |
|:--|:--|:--|
| `data-curator` | 需要专业课程/就业数据 | `01_data/` |
| `scriptwriter` | 写或改单集剧本 | `02_script/episodes/` |
| `storyboard-director` | 剧本定稿后拆分镜 | `03_storyboard/EPnn/` |
| `prompt-engineer` | 分镜表就绪后生成提示词 | `04_prompts/EPnn/` |
| `continuity-auditor` | 每层产物完成后审计 | 只读，输出判决 |
| `pipeline-coder` | 有 SPEC 的管线编码 | `07_pipeline/` |
| `pipeline-reviewer` | 代码 diff 复审 | 只读，输出判决 |
| `pipeline-tester` | 验收标准执行 | 只读，输出判决 |

**自建判据**（五条取其一即可）：① 跨会话记忆 ② 固定输出格式 ③ 需收紧工具面 ④ 有专属陷阱清单 ⑤ 同一职责 ≥3 次/月。

**反面条**：只读几个文件 → `Explore`；只想方案 → `Plan`；只跑命令 → 主会话 Bash。

**档位判据**（命中任一条升 T2）：触及 schema/角色锁/公共命名、改动 ≥5 文件、删除或移动产物、不可逆、根因不明、多解、新增依赖、验收无法单命令表达。

**T2 三腿映射**（本期不实现 router）：施工 = 对应生产岗；复审 = `continuity-auditor` / `pipeline-reviewer`；对抗 = `pipeline-tester` / `episode-gate`。

**结构性约束**：所有代理卡 `tools` 不得包含 `Agent`。判据：`grep -n '^tools:' .claude/agents/*.md | grep Agent` 输出必须为空。

## §5 硬性规则

| 规则 | 理由 |
|:--|:--|
| 写 `04_prompts/EPnn/S*.json` 必须引用角色锁并带 lock digest | 不锁脸，40-60 个镜头跨集必崩 |
| 数据每条必须带 `source_url` + `retrieved_at` + `year` | 面向高中生，错数据比没数据更糟 |
| 不采集、不展示导师信息 | 本期内容只做课程与就业，避免不可核验的导师画像 |
| 已定稿产物不得原地覆盖，版本号递增 | 保住回滚与对拍能力 |
| 不得把标称上下文当有效上下文 | 国产模型实测有效窗口低于标称 |
| 未跑 `validate.py gate EPnn` 不得说该集完成 | 无验证的「完成」等于静默降级 |
| 主角未定选前不得硬编码「烈」或「镜」 | 双版本试播策略尚未定案 |
| 代理/skill 正文不得写进度、绝对路径、凭据 | 定义每次会话加载，进度会变成过期快照 |
| 产品模型必须 pin 明确 ID，不用别名 | 别名会静默切换导致产出漂移 |
| 禁止混用表 A 与表 B 的路由 | 一套是产品运行时，一套是开发期派发 |
| 不读写 `.env`、密钥、`*pem`、`*key`、credentials | 凭据不进入模型上下文与产物 |
| 不主动 `git commit` / `push` / `--force` | 版本动作需用户确认 |
