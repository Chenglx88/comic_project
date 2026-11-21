#!/usr/bin/env python3
"""Hook 公共工具：stdin 契约、路径解析、前瞻内容重建、阻断输出、日志。

所有策略性异常一律 fail-open（返回 0），只有明确判定为违规才返回 2。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def load_payload():
    """读取 stdin JSON。解析失败返回 None，调用方据此 fail-open。"""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - fail-open
        return None


def resolve_target(payload: dict, root: Path):
    """返回 (tool_name, absolute_path)；字段缺失返回 None。"""
    try:
        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return None
        raw_path = tool_input.get("file_path") or tool_input.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        path = Path(raw_path)
        if not path.is_absolute():
            cwd = payload.get("cwd")
            base = Path(cwd) if isinstance(cwd, str) and cwd else root
            path = base / path
        return tool_name, path.resolve()
    except Exception:  # noqa: BLE001
        return None


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def prospective_content(payload: dict, path: Path, tool_name: str):
    """返回写入后的完整文件内容；无法重建时返回 None（fail-open）。"""
    tool_input = payload.get("tool_input") or {}
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    if tool_name == "Edit":
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        try:
            current = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return None
        if old not in current:
            return None
        return current.replace(old, new, 1)
    return None


def canonical_digest(obj) -> str:
    """角色锁 digest 的唯一算法：sort_keys + 紧凑分隔符 + UTF-8。"""
    canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_project_path(ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    return (project_root() / path).resolve()


def log(decision: str, hook: str, path: str, code: str = "") -> None:
    try:
        root = project_root()
        log_path = root / ".state" / "hook.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}\t{decision}\t{hook}\t{path}\t{code}\n")
    except Exception:  # noqa: BLE001 - 日志失败静默
        pass


def emit_block(hook: str, path: str, code: str, reason: str, fix: str) -> int:
    message = f"[{hook}] {code} {path}: {reason} 修复：{fix}"
    print(message, file=sys.stderr)
    log("block", hook, path, code)
    return 2


def emit_allow(hook: str, path: str) -> int:
    log("allow", hook, path)
    return 0


def read_json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def main_guard(fn) -> int:
    """统一异常兜底：任何未预期异常都 fail-open。"""
    try:
        return fn()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        return 0
