# 单集剧本模板

## 五段结构

| 段 | 建议区间 | 作用 | 必须包含 |
|:--|:--|:--|:--|
| 1 开场 | 0-30s | 五境场景与钩子 | 本集专业问题的第一次露头 |
| 2 冲突 | 30-70s | 专业问题具象化 | 一个可感知的失败或困境 |
| 3 试炼 | 70-110s | 用专业知识解题 | 至少 2 个知识点的应用 |
| 4 转折 | 110-150s | 误区的代价或反转 | 常见误区被点破 |
| 5 收束 | 150-180s | 知识点回收 + 下集钩子 | 3 个知识点各回收一次 |

合计必须落在 170-190 秒。

## JSON 骨架

```json
{
  "episode_id": "EP01",
  "major": "计算机科学与技术",
  "major_en": "computer",
  "realm": "修仙境",
  "protagonist": "undecided",
  "logline": "一句话钩子，至少 10 字",
  "beats": [
    {"index": 1, "name": "开场", "start_sec": 0, "end_sec": 30, "summary": ""},
    {"index": 2, "name": "冲突", "start_sec": 30, "end_sec": 70, "summary": ""},
    {"index": 3, "name": "试炼", "start_sec": 70, "end_sec": 110, "summary": ""},
    {"index": 4, "name": "转折", "start_sec": 110, "end_sec": 150, "summary": ""},
    {"index": 5, "name": "收束", "start_sec": 150, "end_sec": 180, "summary": ""}
  ],
  "knowledge_points": [
    {"id": "K1", "title": "", "explain": "", "misconception": "", "source_ref": ""}
  ],
  "characters": ["试炼者", "藏经阁老者"],
  "mentor_portrait": {
    "imagery": "",
    "metrics": ["人才称号", "引用与 h-index", "国家级奖项与学科评估"],
    "note": "三项硬指标综合画像，非官方排名"
  },
  "next_episode_hook": "",
  "continuity": {"prev_summary": "", "open_threads": []},
  "sources": [{"url": "", "retrieved_at": "YYYY-MM-DD", "year": 2026}]
}
```

## 交稿前检查

- [ ] 5 个 beat 索引覆盖 1-5，合计 170-190 秒
- [ ] 知识点 ≥3，每条有 `source_ref` 且对上 `sources`
- [ ] `mentor_portrait.note` 含「综合画像」
- [ ] 主角未定选时 `protagonist` 为 `undecided`
- [ ] 上集悬念已回收，下集钩子已留下
- [ ] `python3 .claude/scripts/validate.py episode <path>` 通过
