"""从模型文本中稳健提取 JSON。"""

from __future__ import annotations

import json


def extract_json(text: str):
    """去围栏并截取第一个 {/[ 到最后一个匹配的 }/]，失败抛 ValueError。"""
    if not isinstance(text, str):
        raise ValueError("输入不是文本")
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise ValueError("未找到 JSON 起始符: " + text[:200])
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    if end < start:
        raise ValueError("JSON 括号不完整: " + text[:200])
    raw = text[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败（前 200 字）: {raw[:200]}") from exc
