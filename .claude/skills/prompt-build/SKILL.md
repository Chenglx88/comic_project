---
name: prompt-build
description: 读分镜表与角色锁，逐镜生成 S###.json 提示词并校验。当用户说「生成提示词」「把分镜转提示词」「补 EP01 的镜头提示词」时使用。只写 04_prompts/EPnn/。
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash(python3 *)
argument-hint: <EPnn>
---

# Prompt Build

分镜 → 单镜提示词 JSON。按角色锁生成，不调用外部 API。

## 1. 读输入

1. `03_storyboard/EPnn/shots.csv`（镜头、时长、运镜、动作）
2. `04_prompts/_shared/protagonist.json`（主角是否定选）
3. `04_prompts/_shared/character_lock.json`（视觉锚点、前缀、seed 区间）
4. `04_prompts/_shared/templates/{shot_prompt,image_prompt,img2video_prompt}.md`
5. `00_schema/shot_prompt.schema.json`

## 2. 计算 digest

```bash
python3 -c "import sys,json;sys.path.insert(0,'.claude/hooks');import _hooklib;print(_hooklib.canonical_digest(json.load(open('04_prompts/_shared/character_lock.json'))))"
```

主角未定选时 digest 写 `sha256:pending`，`protagonist` 写 `undecided`。

## 3. 生成 S###.json

- S001：`consistency.method = "text2img"`，`reference_image` 留空。
- 其余：`consistency.method = "img2img"`，`reference_image` 指向首镜关键帧。
- `text2img.prompt` 以角色 `prompt_prefix` 开头；`seed` 落在 `seed_range`。
- `img2video.prompt` 写动作与运镜，不重复静态外观。
- 负面词覆盖：糊、低清、多指、文字、水印。

## 4. 校验

```bash
python3 .claude/scripts/validate.py prompts 04_prompts/EPnn
```

失败即修；连续 2 次不过就停下报告，不试错式乱改。

## 5. 报告

压缩判决 JSON；`artifacts` 列全部 `S###.json`，`gates` 写校验结果。

## 禁止

- 不调用任何外部图像/视频 API。
- 不改分镜表、剧本、schema 或角色锁。
- 不省略 `character_lock_ref` / `character_lock_digest` / `seed`。
- 不在主角定选后继续写另一主角的提示词。
- 不把未校验的产物标为 `DONE`。
