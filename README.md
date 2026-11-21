# 《五境试炼》项目说明

3 分钟 2D 动漫 × 大学专业科普。首批 36 集，按五境分组。本仓库同时承载内容生产资产与 Claude Code 协作配置。

## 1. 项目结构

```text
comic_project/
├── CLAUDE.md                       # 协作入口：模块依赖、命令、派发、硬规则
├── README.md                       # 本文件：结构、环境、启动
├── TODO.md                         # 待办、缺口、决策登记
├── KNOWN_ISSUES.md                 # 已知问题事实源
├── comic_project_plan.md           # 内容设定与业务方案（权威源，不改）
├── .gitignore
├── .state/                         # 在飞任务进度（唯一权威源，git 忽略）
│   ├── README.md                   # 写者/读者与文件规范
│   ├── STATUS.md                   # 在飞集数表
│   ├── BLOCKERS.md                 # 阻塞条目
│   ├── checkpoints/                # EPnn.json 恢复点
│   ├── specs/                      # 任务 SPEC
│   ├── plans/                      # 施工计划
│   └── verdicts/                   # 压缩判决归档
├── .claude/
│   ├── settings.json               # hooks 注册
│   ├── scripts/
│   │   └── validate.py             # 统一校验入口（标准库）
│   ├── hooks/
│   │   ├── _hooklib.py             # stdin 契约、路径解析、日志
│   │   ├── guard_paths.py          # PreToolUse：命名与路径
│   │   ├── guard_character_lock.py # PreToolUse：角色锁
│   │   ├── validate_artifacts.py   # PostToolUse：产物 schema
│   │   └── selftest_hooks.py       # 正负用例自检
│   ├── prompts/
│   │   ├── T0.md                   # 单镜/单句修正档
│   │   ├── T1.md                   # 单集生产档
│   │   └── T2.md                   # 跨集/管线改造档（本期仅规范）
│   ├── agents/
│   │   ├── data-curator.md
│   │   ├── scriptwriter.md
│   │   ├── storyboard-director.md
│   │   ├── prompt-engineer.md
│   │   ├── continuity-auditor.md
│   │   ├── pipeline-coder.md
│   │   ├── pipeline-reviewer.md
│   │   ├── pipeline-tester.md
│   │   └── agent-memory/<name>/MEMORY.md   # 8 份记忆索引
│   └── skills/
│       ├── episode-kickoff/SKILL.md
│       ├── episode-gate/SKILL.md
│       ├── prompt-build/SKILL.md
│       └── render-orchestrate/SKILL.md
├── 00_schema/                      # 机器契约
│   ├── majors.json                 # 36 个首批专业
│   ├── episode.schema.json
│   ├── storyboard_headers.json
│   ├── shot_prompt.schema.json
│   └── character_lock.schema.json
├── 01_data/
│   ├── raw/                        # 原始检索结果
│   ├── structured/                 # <major_en>.json 结构化数据
│   └── rankings/                   # <major_en>.json 导师综合画像
├── 02_script/
│   ├── world_bible.md              # 世界观与五境规则
│   ├── character_bible.md          # 角色口癖与关系
│   ├── episode_template.md         # 单集结构模板
│   └── episodes/                   # EPnn_<major_en>.json
├── 03_storyboard/
│   └── EPnn/                       # shots.csv / dialogue.csv / foley.csv
├── 04_prompts/
│   ├── _shared/
│   │   ├── protagonist.json        # 主角选择唯一权威
│   │   ├── character_lock.json     # 角色锁（视觉锚点/色值/seed/前缀）
│   │   └── templates/
│   │       ├── image_prompt.md
│   │       ├── img2video_prompt.md
│   │       └── shot_prompt.md
│   └── EPnn/                       # S###.json 单镜提示词
├── 05_assets/
│   ├── characters/                 # 角色设定图与表情差分
│   ├── realms/                     # 五境场景资产
│   ├── props/                      # 道具
│   └── audio/                      # 配音、音乐、音效
├── 06_render/
│   ├── keyframes/                  # 关键帧
│   ├── videos/                     # 单镜视频
│   └── episodes/                   # 拼接成片
└── 07_pipeline/                    # 产品流水线代码（待建）
    ├── README.md
    └── prompts/                    # L1.md ~ L6.md 分层提示词模板
```

空目录以 `.gitkeep` 占位。`.state/`、渲染产物与凭据类文件见 `.gitignore`。

## 2. 环境与运行

**环境**：Python 3.12.3。校验器与 hooks 只依赖标准库，无需安装第三方包。

**日一门禁**（在项目根执行）：

```bash
python3 .claude/scripts/validate.py schema
python3 .claude/scripts/validate.py lock
python3 .claude/scripts/validate.py docs
python3 .claude/scripts/validate.py all
python3 .claude/hooks/selftest_hooks.py
python3 -m compileall -q .claude 07_pipeline
python3 -m json.tool .claude/settings.json >/dev/null
```

**单集校验**：

```bash
python3 .claude/scripts/validate.py episode 02_script/episodes/EP01_computer.json
python3 .claude/scripts/validate.py storyboard 03_storyboard/EP01
python3 .claude/scripts/validate.py prompts 04_prompts/EP01
python3 .claude/scripts/validate.py gate EP01
```

**启用协作配置**：在项目根启动 Claude Code，`.claude/settings.json` 的 hooks 自动生效；8 个代理与 4 个 skill 由 Claude Code 自动发现。

**待生效门禁**：`07_pipeline/` 落地并安装依赖后启用 `pytest -x`、`ruff check .`、`mypy 07_pipeline`。安装前不得声称通过。

## 3. 数据与外部工具

- 专业数据：院校官网、教育部学科评估公开信息、公开学术数据库；每条必须带 URL、检索日期、年份。
- 图像：NovelAI 或 ComfyUI（首镜文生图、后续图生图）。
- 视频：可灵 / Vidu / Seedance 等图生视频工具。
- 后期：Live2D、After Effects、剪映。
- API key 与凭据只放在本地环境变量，不进入仓库、不写入产物、不出现在会话中。

本期不接入任何模型 API，不生成图片或视频；`07_pipeline/` 仅为后续代码预留。

## 4. 维护规则

- 五份文档分工固定：本文件管结构与运行，`CLAUDE.md` 管调度与硬规则，`TODO.md` 管待办与决策，`KNOWN_ISSUES.md` 管缺陷事实，`.state/` 管进度。
- 进度只写 `.state/`；README 与 TODO 不写进度。
- 修改 `00_schema/` 必须同步更新 `validate.py` 与 `selftest_hooks.py`，并重跑 `validate.py all` 与 selftest。
- 新增或改名受限目录时，同步更新 `guard_paths.py` 的规则。
- hooks 对解析异常 fail-open；PostToolUse 无法撤销已落盘文件，只能回灌错误。该限制见 `KNOWN_ISSUES.md`。
