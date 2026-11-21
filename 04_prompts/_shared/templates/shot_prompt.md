# 单镜提示词 JSON 模板

## 骨架

```json
{
  "shot_id": "S001",
  "protagonist": "undecided",
  "character_lock_ref": "04_prompts/_shared/character_lock.json",
  "character_lock_digest": "sha256:pending",
  "seed": 1500,
  "text2img": {
    "prompt": "<角色锁前缀> <主体与动作>，<场景>，<景别>，<光线>，2D anime cel shading",
    "negative_prompt": "blurry, lowres, extra fingers, text, watermark",
    "params": {"width": 1024, "height": 576, "steps": 28, "cfg_scale": 7}
  },
  "img2video": {
    "prompt": "<动作>，<运镜>",
    "first_frame": "06_render/keyframes/EP01_computer_S001_v1.png",
    "last_frame": "",
    "params": {"duration_sec": 4}
  },
  "consistency": {
    "method": "text2img",
    "reference_image": ""
  },
  "notes": ""
}
```

## 规则

- `shot_id` 与文件名一致，三位编号。
- S001 的 `consistency.method` 必须是 `text2img`；其余为 `img2img`，`reference_image` 指向首镜关键帧。
- `protagonist` 只能取 `undecided` / `lie` / `mirror`；已定选时必须与 `protagonist.json` 一致。
- `character_lock_digest` 用 `_hooklib.canonical_digest` 计算；未定选写 `sha256:pending`。
- `seed` 必须是整数；已定选时必须落在角色锁 `seed_range` 内。
- `text2img.prompt` 必须包含角色锁 `prompt_prefix`（未定选除外）。
- 不写外部 API 调用参数、账号、密钥。
