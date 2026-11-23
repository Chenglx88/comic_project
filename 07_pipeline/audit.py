"""L6 质检：文本门禁、媒体门禁与审计报告。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import compose
import config as config_module
import jsonutil
import media_vision
import state

PROJECT_ROOT = config_module.PROJECT_ROOT
VALIDATOR = PROJECT_ROOT / ".claude" / "scripts" / "validate.py"
HOOK_SELFTEST = PROJECT_ROOT / ".claude" / "hooks" / "selftest_hooks.py"
OUTPUT = PROJECT_ROOT / "05_assets" / f"EP01_audit_v{config_module.MEDIA_VERSION}.json"


def _command(label: str, cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    output = (proc.stdout + proc.stderr).strip()
    return {
        "label": label,
        "command": " ".join(cmd),
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output_tail": output.splitlines()[-10:],
    }


def run(final_path: str | None = None) -> dict:
    checks = [
        _command("episode-gate", [sys.executable, str(VALIDATOR), "gate", "EP01"]),
        _command("validate-all", [sys.executable, str(VALIDATOR), "all"]),
        _command("hook-selftest", [sys.executable, str(HOOK_SELFTEST)]),
        _command("compileall", [sys.executable, "-m", "compileall", "-q", ".claude", "07_pipeline"]),
    ]
    blocking: list[str] = []
    major: list[str] = []
    minor: list[str] = []
    for check in checks:
        if not check["ok"]:
            blocking.append(f"{check['label']} 失败: " + " | ".join(check["output_tail"]))
    if final_path:
        path = Path(final_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.is_file():
            blocking.append(f"成片不存在: {path}")
        else:
            errors = compose.validate_final(path)
            if errors:
                blocking.extend(errors)
            else:
                minor.append("成片机器校验通过")
    else:
        major.append("未提供成片路径，媒体门禁未执行")
    keyframe_dir = PROJECT_ROOT / "06_render" / "keyframes"
    samples = [
        keyframe_dir / f"EP01_computer_{shot}_v{config_module.MEDIA_VERSION}.png"
        for shot in ("S001", "S010", "S020", "S030", "S046")
    ]
    samples = [path for path in samples if path.is_file()]
    if not samples:
        visual = "需人工：没有可抽检的关键帧"
    else:
        prompt = (
            "你是动画质检员。逐张检查：主角是否保持同一人（蓬乱红发、右颊疤、金纹护额、"
            "玄色短袍、红腰带）、是否有文字/水印/签名、是否有明显畸形（多指、断肢、面部崩坏）。"
            "只返回 JSON：{\"blocking\":[],\"major\":[],\"minor\":[],\"notes\":\"\"}。"
            "blocking 只放无法交付的问题；major 放需修复的问题；minor 放可选优化。"
        )
        try:
            result = media_vision.audit_images(samples, prompt)
            parsed = jsonutil.extract_json(result["text"])
            if not isinstance(parsed, dict):
                raise ValueError("视觉审计未返回 JSON 对象")
            visual = {"status": "done", "model": result["model"], "result": parsed}
            blocking.extend(str(item) for item in parsed.get("blocking", []))
            major.extend(str(item) for item in parsed.get("major", []))
            minor.extend(str(item) for item in parsed.get("minor", []))
        except (media_vision.MediaError, ValueError) as exc:
            visual = {"status": "需人工", "error": str(exc)}
            major.append("豆包视觉抽检未完成: " + str(exc))
    report = {
        "episode": "EP01",
        "final": final_path,
        "checks": checks,
        "visual_audit": visual,
        "blocking": blocking,
        "major": major,
        "minor": minor,
        "verdict": "PASS" if not blocking and not major else "BLOCKED",
    }
    state.write_json(OUTPUT, report)
    return {
        "verdict": report["verdict"],
        "blocking": len(blocking),
        "major": len(major),
        "minor": len(minor),
        "report": str(OUTPUT),
    }
