#!/usr/bin/env python3
"""PostToolUse(Write|Edit)：产物 schema 校验。

按路径识别产物类型，调用 00_schema 驱动的 validate.py。
PostToolUse 不能撤销写入，只回灌错误；错误明细写 stderr 并返回 2。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import _hooklib as lib

HOOK = "validate_artifacts"

EPISODE_PATH = re.compile(r"^02_script/episodes/EP\d{2}_[a-z0-9_]+\.json$")
STORYBOARD_PATH = re.compile(r"^03_storyboard/EP\d{2}/(shots|dialogue|foley)\.csv$")
PROMPT_PATH = re.compile(r"^04_prompts/EP\d{2}/S\d{3}\.json$")


def load_validator():
    path = Path(__file__).resolve().parent.parent / "scripts" / "validate.py"
    spec = importlib.util.spec_from_file_location("comic_validate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # validate.py 里的相对路径解析应对齐当前项目根（自检时会被指向 fixture）。
    module.ROOT = lib.project_root()
    return module


def full_command(kind: str, path: Path, root: Path) -> str:
    if kind == "episode":
        return f"python3 .claude/scripts/validate.py episode {path.relative_to(root).as_posix()}"
    if kind == "storyboard":
        return f"python3 .claude/scripts/validate.py storyboard-file {path.relative_to(root).as_posix()}"
    return f"python3 .claude/scripts/validate.py prompts {path.parent.relative_to(root).as_posix()}"


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

    if EPISODE_PATH.fullmatch(rel):
        kind = "episode"
    elif STORYBOARD_PATH.fullmatch(rel):
        kind = "storyboard"
    elif PROMPT_PATH.fullmatch(rel):
        kind = "prompt"
    else:
        return lib.emit_allow(HOOK, rel)

    if not path.exists():
        return lib.emit_allow(HOOK, rel)

    try:
        validator = load_validator()
    except Exception:  # noqa: BLE001 - 校验器异常 fail-open
        return 0

    report = validator.Report(rel)
    if kind == "episode":
        validator.validate_episode(path, report)
    elif kind == "storyboard":
        validator.validate_storyboard_file(path, report)
    else:
        validator.validate_prompts(path.parent, report)

    for item in report.warnings[:3]:
        print(f"[warn] {item}", file=sys.stderr)
    if not report.errors:
        return lib.emit_allow(HOOK, rel)

    for item in report.errors[:3]:
        print(f"[error] {item}", file=sys.stderr)
    if len(report.errors) > 3:
        print(f"[error] ... 另有 {len(report.errors) - 3} 条", file=sys.stderr)
    print(
        f"[{HOOK}] INVALID_ARTIFACT {rel}: 共 {len(report.errors)} 个错误。"
        f"完整校验：{full_command(kind, path, root)}",
        file=sys.stderr,
    )
    lib.log("block", HOOK, rel, "INVALID_ARTIFACT")
    return 2


if __name__ == "__main__":
    raise SystemExit(lib.main_guard(run))
