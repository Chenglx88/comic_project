"""运行状态、时间戳、脱敏日志与阻塞项落盘。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".state"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(moment: datetime | None = None) -> str:
    moment = moment or utc_now()
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, data) -> Path:
    """原子写 JSON，避免中断留下半文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def log_response(
    layer: str,
    result: dict,
    episode: str = "EP01",
    stamp: str | None = None,
    root: Path | None = None,
) -> Path:
    """只写模型、HTTP、usage、finish_reason 与 content 前 500 字，不含请求头与 key。"""
    root = Path(root) if root is not None else PROJECT_ROOT
    target = root / ".state" / "runs" / episode / layer / (stamp or utc_stamp()) / "response.json"
    safe = {
        "layer": layer,
        "model": result.get("model"),
        "http_status": result.get("http_status"),
        "usage": result.get("usage"),
        "finish_reason": result.get("finish_reason"),
        "content_preview": str(result.get("content") or "")[:500],
    }
    return write_json(target, safe)


def append_blocker(
    message: str,
    date: str | None = None,
    path: Path | None = None,
) -> str:
    """追加一条 B-YYYYMMDD-NN，绝不覆盖已有条目。返回新编号。"""
    day = date or utc_now().strftime("%Y%m%d")
    target = Path(path) if path is not None else STATE_DIR / "BLOCKERS.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    pattern = re.compile(rf"B-{day}-(\d{{2}})")
    used = [int(match.group(1)) for match in pattern.finditer(existing)]
    number = max(used, default=0) + 1
    blocker_id = f"B-{day}-{number:02d}"
    header = "" if existing else "# BLOCKERS\n\n"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"{header}- {blocker_id}：{message}\n")
    return blocker_id
