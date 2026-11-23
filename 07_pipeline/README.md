# 07_pipeline

产品运行时流水线目录。Phase 1 已落地配置、统一 LLM 客户端与 L1-L3；L4-L6 待建。

## 已落地模块（Phase 1）

| 文件 | 对应层 | 职责 |
|:--|:--|:--|
| `config.py` | 全局 | 安全加载 `.env`、routing、脱敏快照 |
| `llm.py` | L1-L3 | OpenAI 兼容客户端，模型 ID 来自配置，失败重试 |
| `l1.py` | L1 | 检索与结构化专业数据 |
| `l2.py` | L2 | 单集剧本生成与校验 |
| `l3.py` | L3 | 分镜三表生成、CSV 写出与校验 |
| `preflight.py` | 全局 | env 键、routing、ffmpeg/ffprobe 预检 |
| `cli.py` | 全局 | `preflight` / `l1` / `l2` / `l3` 子命令 |
| `tests/test_phase1.py` | 离线测试 | 配置、JSON、校验、CSV、重试，不触网 |

## 计划中的模块

| 文件 | 对应层 | 职责 |
|:--|:--|:--|
| 待建 | L4 | 注入角色锁、生成单镜提示词包 |
| 待建 | L5 | 汇总关键帧、视频、音频，输出成片 |

## 目录

```text
07_pipeline/
├── README.md
└── prompts/
    ├── L1.md   # 数据层
    ├── L2.md   # 剧本层
    ├── L3.md   # 分镜层
    ├── L4.md   # 提示词层
    ├── L5.md   # 渲染编排
    └── L6.md   # 质检层
```

## 落地规则

- 先有 SPEC 再写代码；SPEC 放 `.state/specs/`。
- 代码只写本目录；契约变更走 `00_schema/` 与用户确认。
- 离线测试优先，不把外部 API 与付费调用放进单测。
- 门禁：`python3 -m compileall -q 07_pipeline`、`pytest -x`、`ruff check .`、`mypy 07_pipeline`（后三者未安装时记 `SKIP`）。
