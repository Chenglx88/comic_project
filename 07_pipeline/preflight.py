"""Phase 1 预检：env 键、routing、ffmpeg/ffprobe。只输出 <set>/<missing>。"""

from __future__ import annotations

import shutil
from pathlib import Path

import config as config_module
import state

PIPELINE_DIR = config_module.PIPELINE_DIR
DEFAULT_BIN_DIR = PIPELINE_DIR / "bin"
LAYER_KEYS = {
    "L1": ["TOKENHUB_API_KEY", "HUNYUAN_MODEL_ID"],
    "L2": ["DASHSCOPE_API_KEY", "QWEN_MODEL_ID"],
    "L3": ["DEEPSEEK_API_KEY", "DEEPSEEK_MODEL_ID"],
    "L4": ["ZHIPU_API_KEY", "GLM_MODEL_ID"],
}
TOOLS = ("ffmpeg", "ffprobe")


def _tool_present(name: str, bin_dir: Path) -> bool:
    return (bin_dir / name).is_file() or shutil.which(name) is not None


def run(
    config_obj: config_module.Config | None = None,
    bin_dir: Path | None = None,
    blockers_path: Path | None = None,
    episode: str = "EP01",
) -> dict:
    cfg = config_obj or config_module.load_config()
    bin_dir = Path(bin_dir) if bin_dir is not None else DEFAULT_BIN_DIR

    layers: dict[str, dict] = {}
    missing: list[str] = []
    for layer, keys in LAYER_KEYS.items():
        snapshot = cfg.redacted_snapshot(keys)
        layers[layer] = {"keys": snapshot}
        missing.extend(key for key, value in snapshot.items() if value == "<missing>")

    try:
        routing = config_module.load_routing()
        routing_ok = routing.get("fallback") == "none"
        routing_error = None if routing_ok else "fallback 不是 none"
    except config_module.ConfigError as exc:
        routing_ok = False
        routing_error = str(exc)

    tools = {name: _tool_present(name, bin_dir) for name in TOOLS}
    tools_missing = [name for name, present in tools.items() if not present]

    blocker_ids: list[str] = []
    if missing or tools_missing or not routing_ok:
        details = []
        if missing:
            details.append("缺少环境变量: " + ", ".join(missing))
        if tools_missing:
            details.append("缺少工具: " + ", ".join(tools_missing))
        if not routing_ok:
            details.append("routing 不可用: " + str(routing_error))
        blocker_ids.append(
            state.append_blocker(
                f"preflight {episode} " + "；".join(details),
                path=blockers_path,
            )
        )

    return {
        "episode": episode,
        "ok": not (missing or tools_missing) and routing_ok,
        "layers": layers,
        "missing": missing,
        "routing": {"ok": routing_ok, "fallback": "none" if routing_ok else routing_error},
        "tools": tools,
        "blockers": blocker_ids,
    }
