# 文生图提示词模板

## 结构

```text
[角色锁前缀] + [主体与动作] + [场景] + [景别与构图] + [光线] + [风格与画质]
```

## 必填

| 段 | 写什么 | 例 |
|:--|:--|:--|
| 角色锁前缀 | 从 `character_lock.json` 原样复制 | `pending`（未定选时不填） |
| 主体与动作 | 谁在做什么，一个主要动作 | 少年抬手挡住飞来的齿轮 |
| 场景 | 五境的子场景 | 蒸汽齿轮大街，黄昏 |
| 景别与构图 | 远景/中景/近景/特写；视线方向 | 中景，人物偏左，右侧留出齿轮塔 |
| 光线 | 主光方向与色温 | 侧逆光，暖橙 |
| 风格 | 日系赛璐璐、2D 动画、干净线稿 | 2D anime cel shading, clean lineart |

## 负面词基线

```text
blurry, lowres, jpeg artifacts, extra fingers, extra limbs, deformed hands,
text, watermark, signature, photorealistic, 3d render
```

## 规则

- 一条提示词只写一个镜头，不写分镜序列。
- 角色外观只靠锁前缀保证；正文不重复改发色、瞳色、服装。
- 不写现实品牌、真人姓名、政治与宗教符号。
- 未定选主角时，用「少年 / 试炼者」等中性称呼，不写「烈」或「镜」。
