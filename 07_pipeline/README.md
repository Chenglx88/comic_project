# 07_pipeline

产品运行时流水线目录。当前只有分层提示词模板，尚无代码。

## 计划中的模块

| 文件 | 对应层 | 职责 |
|:--|:--|:--|
| `data_pipeline.py` | L1 | 检索与结构化专业数据 |
| `llm_router.py` | L1-L6 | 按任务类型路由模型，pin 明确模型 ID |
| `prompt_builder.py` | L4 | 注入角色锁、生成单镜提示词包 |
| `compose.py` | L5 | 汇总关键帧、视频、音频，输出成片 |

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
