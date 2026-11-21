---
name: render-orchestrate
description: 为单集生成渲染清单与可粘贴的图/视频工具参数，并登记人工产物。当用户说「出图」「渲染这集」「跑 L5」「生成渲染清单」时使用。写 06_render/EPnn/render_manifest.json。
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(python3 *)
argument-hint: <EPnn>
---

# Render Orchestrate

L5 渲染编排。产出清单与参数，不直接调用外部服务。

## 1. 前置检查

- `04_prompts/EPnn/S*.json` 齐全，且 `validate.py prompts 04_prompts/EPnn` 通过。
- S001 为 `text2img`；其余为 `img2img`。
- `04_prompts/_shared/protagonist.json` 与提示词一致。

任一不满足 → 停止并报 `BLOCKED`，不生成清单。

## 2. 生成渲染清单

写 `06_render/EPnn/render_manifest.json`：

```json
{
  "episode_id": "EP01",
  "generated_at": "YYYY-MM-DDTHH:MM:SS",
  "track": "keyframe",
  "shots": [
    {"shot_id": "S001", "method": "text2img", "seed": 1500,
     "prompt_file": "04_prompts/EP01/S001.json",
     "output": "06_render/keyframes/EP01_computer_S001_v1.png",
     "status": "pending"}
  ],
  "manual_steps": ["首镜定标后人工确认脸型", "视频拼接", "配音对轨"]
}
```

- 所有 `status` 初始为 `pending`；只有文件真实存在且通过人工确认后才改 `done`。
- 输出路径必须符合 `EP{集号}_{专业英文}_S{镜号}_v{版本}.{png|mp4|wav}`。

## 3. 输出可粘贴参数

按镜头逐条给出：

- 文生图：prompt、negative_prompt、seed、尺寸、steps、CFG。
- 图生视频：首帧路径、动作 prompt、时长、运镜。
- 音频：台词文本、情绪、建议音色。

只输出参数块，不替用户调用工具。

## 4. 登记人工产物

用户回填实际产物后：

1. 核对文件名与 `render_manifest.json` 一致。
2. 把对应 `status` 改为 `done`。
3. 跑 `python3 .claude/scripts/validate.py all`。

## 禁止

- 不上传素材到任何外部服务，不替用户点「生成」。
- 不修改提示词、分镜、角色锁或 schema。
- 不跳过 S001 定标直接批量图生图。
- 不把未生成或未确认的文件登记为 `done`。
- 不在提示词包未通过校验时生成清单。
