#!/usr/bin/env python3
"""PreToolUse(Write|Edit)：角色锁守卫。

只检查 04_prompts/EPnn/S###.json。
- 任何阶段：JSON 可解析、character_lock_ref 指向存在的锁。
- 主角已定选：protagonist 一致、digest 匹配、prompt 含锁前缀、seed 在区间内。
"""

from __future__ import annotations

import json
import re

import _hooklib as lib

HOOK = "guard_character_lock"
PROMPT_PATH = re.compile(r"^04_prompts/EP\d{2}/S\d{3}\.json$")


def load_selection(root):
    path = root / "04_prompts" / "_shared" / "protagonist.json"
    if not path.exists():
        return "undecided", None
    data, err = lib.read_json_file(path)
    if err:
        return "undecided", f"protagonist.json 解析失败: {err}"
    return str(data.get("selected", "undecided")), None


def run() -> int:
    payload = lib.load_payload()
    if payload is None:
        return 0
    root = lib.project_root()
    target = lib.resolve_target(payload, root)
    if target is None:
        return 0
    tool_name, path = target
    if tool_name not in ("Write", "Edit"):
        return 0
    if not lib.is_inside(path, root):
        return 0  # 路径越界由 guard_paths 负责
    rel = lib.relative_path(path, root)
    if not PROMPT_PATH.fullmatch(rel):
        return lib.emit_allow(HOOK, rel)

    content = lib.prospective_content(payload, path, tool_name)
    if content is None:
        return lib.emit_allow(HOOK, rel)  # Edit 重建失败：fail-open

    try:
        data = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        return lib.emit_block(
            HOOK, rel, "BAD_JSON", f"提示词 JSON 解析失败: {exc}",
            "修正 JSON 后重写；结构见 00_schema/shot_prompt.schema.json",
        )
    if not isinstance(data, dict):
        return lib.emit_block(HOOK, rel, "BAD_JSON", "提示词应为 JSON 对象", "见 00_schema/shot_prompt.schema.json")

    ref = data.get("character_lock_ref")
    if not isinstance(ref, str) or not ref.strip():
        return lib.emit_block(
            HOOK, rel, "LOCK_MISSING", "缺少 character_lock_ref",
            "填写 04_prompts/_shared/character_lock.json 并重写本镜",
        )
    lock_path = lib.resolve_project_path(ref)
    if not lock_path.exists():
        return lib.emit_block(
            HOOK, rel, "LOCK_MISSING", f"角色锁文件不存在: {ref}",
            "确认 character_lock_ref 指向 04_prompts/_shared/character_lock.json",
        )

    selected, selection_error = load_selection(root)
    if selection_error:
        return lib.emit_block(HOOK, rel, "LOCK_MISSING", selection_error, "修复 protagonist.json")

    if selected == "undecided":
        return lib.emit_allow(HOOK, rel)

    if data.get("protagonist") != selected:
        return lib.emit_block(
            HOOK, rel, "LOCK_STALE",
            f"主角已定选 {selected}，本镜写的是 {data.get('protagonist')}",
            "改为已定选主角，或先更新 protagonist.json（需用户裁决）",
        )

    lock, err = lib.read_json_file(lock_path)
    if err:
        return lib.emit_block(HOOK, rel, "LOCK_STALE", f"角色锁解析失败: {err}", "修复 character_lock.json")
    expected_digest = lib.canonical_digest(lock)
    if data.get("character_lock_digest") != expected_digest:
        return lib.emit_block(
            HOOK, rel, "LOCK_STALE",
            "character_lock_digest 与当前角色锁不一致",
            f"重算 digest：{expected_digest}",
        )

    character = (lock.get("protagonists") or {}).get(selected) or {}
    prefix = character.get("prompt_prefix")
    prompt = ((data.get("text2img") or {}).get("prompt") or "")
    if isinstance(prefix, str) and prefix not in ("", "pending") and prefix not in prompt:
        return lib.emit_block(
            HOOK, rel, "LOCK_PREFIX_MISSING",
            "text2img.prompt 未包含角色锁 prompt_prefix",
            "把 prompt_prefix 原样前置到 text2img.prompt",
        )

    seed_range = character.get("seed_range")
    seed = data.get("seed")
    if isinstance(seed_range, list) and len(seed_range) == 2 and isinstance(seed, int) and not isinstance(seed, bool):
        if not seed_range[0] <= seed <= seed_range[1]:
            return lib.emit_block(
                HOOK, rel, "SEED_OUT_OF_RANGE",
                f"seed {seed} 不在 {seed_range} 内",
                "改用角色锁 seed_range 内的 seed",
            )
    return lib.emit_allow(HOOK, rel)


if __name__ == "__main__":
    raise SystemExit(lib.main_guard(run))
