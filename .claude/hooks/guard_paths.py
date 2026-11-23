#!/usr/bin/env python3
"""PreToolUse(Write|Edit)：命名与路径守卫。

规则：
- 写入路径必须落在项目根内；
- 受限目录的文件名必须匹配约定；
- 其余路径放行（避免把自由文档写入误伤）。
"""

from __future__ import annotations

import re

import _hooklib as lib

HOOK = "guard_paths"

RESTRICTED = [
    (re.compile(r"^01_data/structured/"), re.compile(r"^[a-z0-9_]+\.json$"),
     "{专业英文}.json，如 computer_science.json"),
    (re.compile(r"^02_script/episodes/"), re.compile(r"^EP\d{2}_[a-z0-9_]+\.json$"),
     "EP{集号}_{专业英文}.json，如 EP01_computer.json"),
    (re.compile(r"^03_storyboard/EP\d{2}/"), re.compile(r"^(shots|dialogue|foley|overlays)\.csv$"),
     "shots.csv / dialogue.csv / foley.csv / overlays.csv"),
    (re.compile(r"^04_prompts/EP\d{2}/"), re.compile(r"^S\d{3}\.json$"),
     "S{镜号三位}.json，如 S001.json"),
    (re.compile(r"^06_render/keyframes/|^06_render/videos/"),
     re.compile(r"^EP\d{2}_[a-z0-9_]+_S\d{3}_v\d+\.(png|jpg|mp4|wav)$"),
     "EP{集号}_{专业英文}_S{镜号}_v{版本}.png"),
    (re.compile(r"^06_render/episodes/"), re.compile(r"^EP\d{2}_final_v\d+\.mp4$"),
     "EP{集号}_final_v{版本}.mp4"),
    (re.compile(r"^06_render/EP\d{2}/"), re.compile(r"^render_manifest\.json$"),
     "render_manifest.json"),
]

ALWAYS_ALLOW = re.compile(
    r"^(\.claude/|\.state/|00_schema/|04_prompts/_shared/|07_pipeline/|01_data/raw/|05_assets/)"
)
ROOT_MARKDOWN = re.compile(r"^[^/]+\.md$")


def judge(rel: str):
    """返回 (code, expected, reason) 或 None。"""
    for dir_re, name_re, expected in RESTRICTED:
        if dir_re.search(rel):
            filename = rel.rsplit("/", 1)[-1]
            if not name_re.fullmatch(filename):
                return "BAD_NAME", expected, f"文件名 {filename!r} 不符合命名规范"
            return None
    if ALWAYS_ALLOW.search(rel):
        return None
    if ROOT_MARKDOWN.fullmatch(rel):
        return None
    if rel.startswith(("02_script/", "03_storyboard/", "04_prompts/", "06_render/")) and rel.endswith(
        ("/shots.csv", "/dialogue.csv", "/foley.csv")
    ):
        return "BAD_NAME", "EP{集号}/ 目录下的分镜三表", "分镜三表必须放在 03_storyboard/EPxx/ 下"
    return None


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
        return lib.emit_block(
            HOOK, str(path), "OUTSIDE_ROOT",
            "写入路径越出项目根目录",
            "只能写项目内路径；检查 file_path 是否被拼成了绝对路径或含 ..",
        )
    rel = lib.relative_path(path, root)
    verdict = judge(rel)
    if verdict is None:
        return lib.emit_allow(HOOK, rel)
    code, expected, reason = verdict
    return lib.emit_block(
        HOOK, rel, code, reason,
        f"改为 {expected}；命名规范见 CLAUDE.md §5 与 00_schema/storyboard_headers.json",
    )


if __name__ == "__main__":
    raise SystemExit(lib.main_guard(run))
