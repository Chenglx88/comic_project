"""L3 分镜层：三表生成、校验、CSV 落盘与回灌修复。"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import config as config_module
import jsonutil
import llm
import state
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
PROMPT_PATH = config_module.PIPELINE_DIR / "prompts" / "L3.md"
HEADERS_PATH = PROJECT_ROOT / "00_schema" / "storyboard_headers.json"
SCRIPT_PATH = PROJECT_ROOT / "02_script" / "episodes" / "EP01_computer.json"
OUTPUT_DIR = PROJECT_ROOT / "03_storyboard" / "EP01"
VALIDATOR = PROJECT_ROOT / ".claude" / "scripts" / "validate.py"
PROMPT_FILE_PATTERN = re.compile(r"S\d{3}\.json")


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


COURSE_EXPLAIN_MARKERS = ("主要学", "学什么", "研究", "核心", "讲的是", "内容")
COURSE_FOUNDATION_MARKERS = ("基础", "先修", "前置", "学过", "入门", "预备", "先学", "先懂", "前提")


def _coverage_errors(script: dict, data: dict) -> list[str]:
    coverage = script.get("coverage") or {}
    dialogue_rows = [str(row.get("text") or "") for row in data.get("dialogue", [])]
    dialogue_text = "\n".join(dialogue_rows)
    overlay_text = "\n".join(
        f"{row.get('title') or ''} {row.get('body') or ''}" for row in data.get("overlays", [])
    )
    course_names = coverage.get("courses", [])
    missing_courses = [name for name in course_names if name not in dialogue_text]
    missing_jobs = [name for name in coverage.get("employment", []) if name not in overlay_text]
    errors: list[str] = []
    if missing_courses:
        errors.append("台词缺少课程名: " + ", ".join(missing_courses))
    if missing_jobs:
        errors.append("信息卡缺少就业方向全名: " + ", ".join(missing_jobs))

    for name in course_names:
        starts = [index for index, text in enumerate(dialogue_rows) if name in text]
        if not starts:
            continue
        start = starts[0]
        later = [
            index
            for index, text in enumerate(dialogue_rows)
            if index > start and any(other in text for other in course_names if other != name)
        ]
        end = min(later) if later else start + 7
        window = "\n".join(dialogue_rows[start:min(end, start + 7)])
        if not any(marker in window for marker in COURSE_EXPLAIN_MARKERS):
            errors.append(f"课程「{name}」缺少主要学习内容讲解")
        if not any(marker in window for marker in COURSE_FOUNDATION_MARKERS):
            errors.append(f"课程「{name}」缺少学习基础/先修说明")
    return errors


def validate_storyboard(data, script: dict | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"]
    for key in ("shots", "dialogue", "foley", "overlays"):
        if not isinstance(data.get(key), list):
            errors.append(f"缺少数组 {key}")
    if errors:
        return errors

    shots = data["shots"]
    dialogue = data["dialogue"]
    foley = data["foley"]
    overlays = data["overlays"]

    if not 40 <= len(shots) <= 60:
        errors.append(f"镜头数 {len(shots)} 越界（40-60）")

    dialogue_ids = set()
    for index, row in enumerate(dialogue):
        if not isinstance(row, dict):
            errors.append(f"dialogue[{index}] 不是对象")
            continue
        dialogue_id = str(row.get("dialogue_id") or "").strip()
        if not dialogue_id:
            errors.append(f"dialogue[{index}] 缺 dialogue_id")
        elif dialogue_id in dialogue_ids:
            errors.append(f"dialogue_id 重复: {dialogue_id}")
        else:
            dialogue_ids.add(dialogue_id)

    seen: set[str] = set()
    total = 0.0
    beats: set[int] = set()
    for index, row in enumerate(shots):
        if not isinstance(row, dict):
            errors.append(f"shots[{index}] 不是对象")
            continue
        expected_id = f"S{index + 1:03d}"
        shot_id = str(row.get("shot_id") or "").strip()
        if shot_id in seen:
            errors.append(f"shot_id 重复: {shot_id}")
        elif shot_id != expected_id:
            errors.append(f"shot_id 应为 {expected_id}，实际 {shot_id}")

        beat = row.get("beat")
        if not isinstance(beat, int) or isinstance(beat, bool) or not 1 <= beat <= 4:
            errors.append(f"{shot_id} beat 应为 1-4")
        else:
            beats.add(beat)

        duration = row.get("duration_sec")
        if not _is_num(duration):
            errors.append(f"{shot_id} duration_sec 不是数字")
        else:
            if not 3 <= duration <= 8:
                errors.append(f"{shot_id} 单镜时长 {duration:g}s 越界（3-8s）")
            total += duration

        prompt_file = str(row.get("prompt_file") or "").strip()
        if not PROMPT_FILE_PATTERN.fullmatch(prompt_file):
            errors.append(f"{shot_id} prompt_file 非法: {prompt_file!r}")

        dialogue_id = str(row.get("dialogue_id") or "").strip()
        if dialogue_id and dialogue_id not in dialogue_ids:
            errors.append(f"{shot_id} 引用了不存在的 dialogue_id: {dialogue_id}")

        reference = str(row.get("reference_shot") or "").strip()
        if reference and reference not in seen:
            errors.append(f"{shot_id} reference_shot 指向不存在或未来的镜头: {reference}")
        seen.add(shot_id)

    if not 200 <= total <= 220:
        errors.append(f"总时长 {total:g}s 越界（200-220s）")
    if beats != {1, 2, 3, 4}:
        errors.append(f"beat 必须覆盖 1-4，实际 {sorted(beats)}")

    overlay_ids: set[str] = set()
    kinds: dict[str, int] = {}
    for index, row in enumerate(overlays):
        if not isinstance(row, dict):
            errors.append(f"overlays[{index}] 不是对象")
            continue
        overlay_id = str(row.get("overlay_id") or "").strip()
        if not re.fullmatch(r"O\d{3}", overlay_id):
            errors.append(f"overlay_id 非法: {overlay_id!r}")
        elif overlay_id in overlay_ids:
            errors.append(f"overlay_id 重复: {overlay_id}")
        else:
            overlay_ids.add(overlay_id)
        kind = str(row.get("kind") or "").strip()
        kinds[kind] = kinds.get(kind, 0) + 1
        if not str(row.get("title") or "").strip() or not str(row.get("body") or "").strip():
            errors.append(f"信息卡 {overlay_id} 的 title/body 不得为空")
        try:
            start = float(row.get("start_sec"))
            end = float(row.get("end_sec"))
        except (TypeError, ValueError):
            errors.append(f"信息卡 {overlay_id} 时间不是数字")
            continue
        if end <= start:
            errors.append(f"信息卡 {overlay_id} 结束时间必须大于开始时间")
        if start < 0 or end > total + 0.01:
            errors.append(f"信息卡 {overlay_id} 时间越界")
    for kind, expected in (("course", 5), ("employment", 5)):
        if kinds.get(kind, 0) != expected:
            errors.append(f"{kind} 信息卡数量应为 {expected}，实际 {kinds.get(kind, 0)}")
    if script is not None:
        errors.extend(_coverage_errors(script, data))

    for index, row in enumerate(foley):
        if not isinstance(row, dict):
            errors.append(f"foley[{index}] 不是对象")
            continue
        cue_id = str(row.get("cue_id") or "").strip()
        if not cue_id:
            errors.append(f"foley[{index}] 缺 cue_id")
        shot_id = str(row.get("shot_id") or "").strip()
        if not shot_id or shot_id not in seen:
            errors.append(f"foley {cue_id or index} 的 shot_id 不存在: {shot_id!r}")
    return errors


def write_tables(data: dict, out_dir: Path, headers: dict) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name in ("shots", "dialogue", "foley", "overlays"):
        path = out_dir / f"{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=headers[name],
                extrasaction="ignore",
                restval="",
            )
            writer.writeheader()
            for row in data.get(name, []):
                writer.writerow({key: row.get(key, "") for key in headers[name]})
        paths[name] = path
    return paths


def load_headers() -> dict:
    return json.loads(HEADERS_PATH.read_text(encoding="utf-8"))


def _messages(script: str, headers: dict) -> list[dict]:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    system = (
        prompt
        + "\n\n## storyboard_headers.json\n"
        + json.dumps(headers, ensure_ascii=False, indent=2)
        + '\n\n只返回一个 JSON 对象：'
        '{"shots": [...], "dialogue": [...], "foley": [...], "overlays": [...]}，'
        "列名必须与 schema 完全一致，不要 Markdown 围栏或解释。"
    )
    user = "## 02_script/episodes/EP01_computer.json\n" + script + "\n\n请只返回 JSON。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _run_validator(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "storyboard", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def _install(temp_dir: Path, target: Path, headers: dict) -> dict[str, Path]:
    target.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in ("shots", "dialogue", "foley", "overlays"):
        destination = target / f"{name}.csv"
        os.replace(temp_dir / f"{name}.csv", destination)
        paths[name] = destination
    return paths


def _summary(data: dict, paths: dict) -> dict:
    total = sum(float(row.get("duration_sec", 0)) for row in data["shots"])
    return {
        "shots": len(data["shots"]),
        "total_duration_sec": round(total, 3),
        "dialogue": len(data["dialogue"]),
        "foley": len(data["foley"]),
        "overlays": len(data.get("overlays") or []),
        "paths": {name: str(path) for name, path in paths.items()},
    }


def run(
    episode: str = "EP01",
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    if episode != "EP01":
        raise PipelineError("Phase 1 仅支持 EP01", code=4)
    headers = load_headers()
    if resume and all(
        (OUTPUT_DIR / f"{name}.csv").is_file()
        for name in ("shots", "dialogue", "foley", "overlays")
    ):
        passed, output = _run_validator(OUTPUT_DIR)
        if not passed:
            raise PipelineError("L3 resume 未通过 validate.py storyboard: " + output)
        data = {
            name: list(csv.DictReader((OUTPUT_DIR / f"{name}.csv").open(encoding="utf-8")))
            for name in ("shots", "dialogue", "foley", "overlays")
        }
        data["shots"] = [
            {**row, "duration_sec": float(row["duration_sec"]), "beat": int(row["beat"])}
            for row in data["shots"]
        ]
        for name in ("overlays",):
            data[name] = [
                {**row, "start_sec": float(row["start_sec"]), "end_sec": float(row["end_sec"])}
                for row in data[name]
            ]
        script_data = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
        errors = validate_storyboard(data, script_data)
        if errors:
            raise PipelineError("L3 resume 校验失败：" + "; ".join(errors))
        return _summary(data, {name: OUTPUT_DIR / f"{name}.csv" for name in data})

    if not SCRIPT_PATH.is_file():
        raise PipelineError(f"L3 缺少输入文件: {SCRIPT_PATH}", code=4)
    if not PROMPT_PATH.is_file():
        raise PipelineError(f"L3 缺少提示词: {PROMPT_PATH}", code=4)
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    script_data = json.loads(script)
    if int(script_data.get("version", 1)) < 2:
        raise PipelineError("L3 需要 v2 剧本（含 coverage），请先重跑 L2", code=7)
    messages = _messages(script, headers)

    errors: list[str] = []
    data = None
    temp_dir: Path | None = None
    try:
        for attempt in range(3):
            result = llm.chat(
                "L3",
                messages,
                max_tokens=32768,
                response_format="json_object",
                config=config_obj,
                episode=episode,
            )
            try:
                data = jsonutil.extract_json(result["content"])
            except ValueError as exc:
                errors = [str(exc)]
            else:
                errors = validate_storyboard(data, script_data)
                if not errors:
                    if temp_dir is None:
                        OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
                        temp_dir = Path(tempfile.mkdtemp(prefix=".EP01-", dir=OUTPUT_DIR.parent))
                    write_tables(data, temp_dir, headers)
                    passed, output = _run_validator(temp_dir)
                    if passed:
                        paths = _install(temp_dir, OUTPUT_DIR, headers)
                        return _summary(data, paths)
                    errors = ["validate.py storyboard 未通过:\n" + output]
            if attempt < 2:
                messages = messages + [
                    {"role": "assistant", "content": result["content"]},
                    {
                        "role": "user",
                        "content": "上次输出未通过校验，请只返回修复后的完整 JSON。错误：\n- "
                        + "\n- ".join(errors),
                    },
                ]
    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    raise PipelineError("L3 校验重试耗尽：" + "; ".join(errors))
