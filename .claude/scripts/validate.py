#!/usr/bin/env python3
"""《五境试炼》统一产物校验入口。

只依赖 Python 标准库。子命令：
  schema                     校验 00_schema/ 自身
  lock [path]                校验角色锁与主角选择一致性
  docs                       校验配置文档、代理卡、skill、settings.json
  episode <path>             校验单集剧本 JSON
  storyboard <EP目录>        校验 shots/dialogue/foley 三张 CSV
  storyboard-file <path>     校验单张分镜 CSV（供 PostToolUse 使用）
  prompts <EP目录>           校验 S###.json 提示词包
  gate <EPnn>                单集总门禁：剧本 + 分镜 + 提示词 + 交叉一致性
  all                        扫描并校验现有全部产物（空集输出 0 artifacts）

退出码：0 = 通过；1 = 有错误。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "00_schema"

REALMS = {"修仙境", "机枢城", "万象医馆", "星渊观测所", "言灵殿"}
PROTAGONISTS = {"undecided", "lie", "mirror"}
AGENT_NAMES = [
    "data-curator",
    "scriptwriter",
    "storyboard-director",
    "prompt-engineer",
    "continuity-auditor",
    "pipeline-coder",
    "pipeline-reviewer",
    "pipeline-tester",
]
SKILL_NAMES = ["episode-kickoff", "episode-gate", "prompt-build", "render-orchestrate"]


# ---------------------------------------------------------------- 基础工具


class Report:
    def __init__(self, label: str) -> None:
        self.label = label
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def emit(self) -> bool:
        for item in self.warnings:
            print(f"[warn] {item}", file=sys.stderr)
        for item in self.errors:
            print(f"[error] {item}", file=sys.stderr)
        if self.errors:
            print(f"[validate] {self.label}: FAILED ({len(self.errors)} errors)")
            return False
        print(f"[validate] {self.label}: OK")
        return True


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001 - 报错给用户看
        return None, str(exc)


def load_schema(name: str):
    data, err = read_json(SCHEMA_DIR / name)
    if err:
        raise SystemExit(f"[validate] 无法读取 00_schema/{name}: {err}")
    return data


def require(obj, keys, where: str, report: Report) -> bool:
    if not isinstance(obj, dict):
        report.error(where, "应为 JSON 对象")
        return False
    missing = [key for key in keys if key not in obj]
    if missing:
        report.error(where, f"缺少字段 {missing}")
        return False
    return True


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def nonempty_str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_csv(path: Path, expected: list[str], report: Report) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = reader.fieldnames or []
            if actual != expected:
                report.error(path, f"表头不符：期望 {expected}，实际 {actual}")
                return []
            return list(reader)
    except Exception as exc:  # noqa: BLE001
        report.error(path, f"读取失败: {exc}")
        return []


def resolve_project_path(ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


# ---------------------------------------------------------------- schema


def validate_schemas(report: Report) -> None:
    names = [
        "majors.json",
        "episode.schema.json",
        "storyboard_headers.json",
        "shot_prompt.schema.json",
        "character_lock.schema.json",
    ]
    loaded = {}
    for name in names:
        path = SCHEMA_DIR / name
        if not path.exists():
            report.error(path, "文件不存在")
            continue
        data, err = read_json(path)
        if err:
            report.error(path, f"JSON 解析失败: {err}")
            continue
        loaded[name] = data

    majors = loaded.get("majors.json", {}).get("majors", [])
    if len(majors) != 36:
        report.error(SCHEMA_DIR / "majors.json", f"首批专业应为 36 条，实际 {len(majors)}")
    seen = set()
    for item in majors:
        if not isinstance(item, dict):
            report.error(SCHEMA_DIR / "majors.json", "条目不是对象")
            continue
        for key in ("major", "major_en", "realm", "hook"):
            if not nonempty_str(item.get(key)):
                report.error(SCHEMA_DIR / "majors.json", f"{item.get('major_en', '?')} 缺 {key}")
        if item.get("realm") not in REALMS:
            report.error(SCHEMA_DIR / "majors.json", f"{item.get('major_en')} 的境非法")
        if item.get("major_en") in seen:
            report.error(SCHEMA_DIR / "majors.json", f"major_en 重复: {item.get('major_en')}")
        seen.add(item.get("major_en"))

    headers = loaded.get("storyboard_headers.json", {})
    expected_keys = {"shots", "dialogue", "foley", "constraints"}
    if set(headers) != expected_keys:
        report.error(SCHEMA_DIR / "storyboard_headers.json", f"键应为 {sorted(expected_keys)}")

    for name in ("episode.schema.json", "shot_prompt.schema.json", "character_lock.schema.json"):
        schema = loaded.get(name, {})
        if not schema.get("required"):
            report.error(SCHEMA_DIR / name, "未声明 required")


# ---------------------------------------------------------------- character lock


def validate_character_lock(path: Path, report: Report) -> None:
    data, err = read_json(path)
    if err:
        report.error(path, f"JSON 解析失败: {err}")
        return
    if not require(data, ["version", "updated", "protagonists"], path, report):
        return
    if not is_int(data["version"]) or data["version"] < 1:
        report.error(path, "version 应为 ≥1 的整数")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data["updated"])):
        report.error(path, f"updated 非法: {data['updated']}")
    protagonists = data["protagonists"]
    if not isinstance(protagonists, dict):
        report.error(path, "protagonists 应为对象")
        return
    required = [
        "display_name",
        "visual_anchors",
        "palette",
        "outfit",
        "expressions",
        "seed_range",
        "reference_images",
        "prompt_prefix",
    ]
    for name in ("lie", "mirror"):
        character = protagonists.get(name)
        if not isinstance(character, dict):
            report.error(path, f"缺角色 {name}")
            continue
        if not require(character, required, f"{path}:{name}", report):
            continue
        if not nonempty_str(character["display_name"]):
            report.error(path, f"{name}.display_name 为空")
        if not isinstance(character["visual_anchors"], list) or not character["visual_anchors"]:
            report.error(path, f"{name}.visual_anchors 至少 1 条")
        if not isinstance(character["expressions"], list) or len(character["expressions"]) < 5:
            report.error(path, f"{name}.expressions 至少 5 条")
        seed_range = character["seed_range"]
        if seed_range is not None:
            if (
                not isinstance(seed_range, list)
                or len(seed_range) != 2
                or not all(is_int(value) for value in seed_range)
                or seed_range[0] > seed_range[1]
            ):
                report.error(path, f"{name}.seed_range 应为两个递增整数或 null")
        if not nonempty_str(character["prompt_prefix"]):
            report.error(path, f"{name}.prompt_prefix 为空")

    selection_path = ROOT / "04_prompts" / "_shared" / "protagonist.json"
    if selection_path.exists():
        selection, selection_err = read_json(selection_path)
        if selection_err:
            report.error(selection_path, f"JSON 解析失败: {selection_err}")
        else:
            selected = selection.get("selected")
            if selected not in PROTAGONISTS:
                report.error(selection_path, f"selected 非法: {selected!r}")
            elif selected != "undecided":
                character = protagonists.get(selected) or {}
                if character.get("seed_range") is None:
                    report.error(path, f"已定选 {selected}，但 seed_range 仍为 null")
                if character.get("prompt_prefix") in (None, "", "pending"):
                    report.error(path, f"已定选 {selected}，但 prompt_prefix 仍为 pending")


# ---------------------------------------------------------------- episode


def validate_episode(path: Path, report: Report):
    data, err = read_json(path)
    if err:
        report.error(path, f"JSON 解析失败: {err}")
        return None
    required = [
        "episode_id",
        "major",
        "major_en",
        "realm",
        "protagonist",
        "logline",
        "beats",
        "knowledge_points",
        "characters",
        "mentor_portrait",
        "next_episode_hook",
        "continuity",
        "sources",
    ]
    if not require(data, required, path, report):
        return data

    if not re.fullmatch(r"EP\d{2}", str(data["episode_id"])):
        report.error(path, f"episode_id 非法: {data['episode_id']}")
    if not re.fullmatch(r"[a-z0-9_]+", str(data["major_en"])):
        report.error(path, f"major_en 非法: {data['major_en']}")
    if data["realm"] not in REALMS:
        report.error(path, f"realm 非法: {data['realm']}")
    if data["protagonist"] not in PROTAGONISTS:
        report.error(path, f"protagonist 非法: {data['protagonist']}")
    if not nonempty_str(data["logline"]) or len(data["logline"]) < 10:
        report.error(path, "logline 至少 10 字")

    beats = data["beats"]
    if not isinstance(beats, list) or len(beats) != 5:
        report.error(path, "beats 必须为 5 段")
    else:
        total = 0.0
        indices = set()
        for beat in beats:
            if not require(beat, ["index", "name", "start_sec", "end_sec", "summary"], path, report):
                continue
            if not is_int(beat["index"]) or not 1 <= beat["index"] <= 5:
                report.error(path, f"beat index 非法: {beat['index']}")
            indices.add(beat["index"])
            if not is_num(beat["start_sec"]) or not is_num(beat["end_sec"]):
                report.error(path, f"beat {beat['index']} 时间不是数字")
                continue
            if beat["end_sec"] <= beat["start_sec"]:
                report.error(path, f"beat {beat['index']} 结束时间必须大于开始时间")
            total += beat["end_sec"] - beat["start_sec"]
        if indices != {1, 2, 3, 4, 5}:
            report.error(path, f"beat index 必须覆盖 1-5，实际 {sorted(indices)}")
        if not 170 <= total <= 190:
            report.error(path, f"beats 总时长 {total:g}s，期望 170-190s")

    points = data["knowledge_points"]
    if not isinstance(points, list) or len(points) < 3:
        report.error(path, "knowledge_points 至少 3 条")
    else:
        for point in points:
            if not require(point, ["id", "title", "explain", "misconception", "source_ref"], path, report):
                continue
            if not nonempty_str(point["source_ref"]):
                report.error(path, f"知识点 {point.get('id')} 缺 source_ref")

    characters = data["characters"]
    if not isinstance(characters, list) or not characters:
        report.error(path, "characters 至少 1 个")
    elif not all(nonempty_str(item) for item in characters):
        report.error(path, "characters 含空值")

    mentor = data["mentor_portrait"]
    if require(mentor, ["imagery", "metrics", "note"], path, report):
        if "综合画像" not in str(mentor["note"]):
            report.error(path, "mentor_portrait.note 必须含「综合画像」")
        if not isinstance(mentor["metrics"], list) or not mentor["metrics"]:
            report.error(path, "mentor_portrait.metrics 至少 1 条")

    continuity = data["continuity"]
    if require(continuity, ["prev_summary", "open_threads"], path, report):
        if not isinstance(continuity["open_threads"], list):
            report.error(path, "continuity.open_threads 应为数组")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        report.error(path, "sources 至少 1 条")
    else:
        for source in sources:
            if not require(source, ["url", "retrieved_at", "year"], path, report):
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(source["retrieved_at"])):
                report.error(path, f"source.retrieved_at 非法: {source['retrieved_at']}")
            if not is_int(source["year"]):
                report.error(path, "source.year 应为整数")

    if not nonempty_str(data["next_episode_hook"]):
        report.error(path, "next_episode_hook 为空")
    return data


# ---------------------------------------------------------------- storyboard


def validate_storyboard(dir_path: Path, report: Report) -> None:
    if not dir_path.is_dir():
        report.error(dir_path, "目录不存在")
        return
    headers = load_schema("storyboard_headers.json")
    constraints = headers.get("constraints", {})

    shots = read_csv(dir_path / "shots.csv", headers["shots"], report)
    dialogue = read_csv(dir_path / "dialogue.csv", headers["dialogue"], report)
    foley = read_csv(dir_path / "foley.csv", headers["foley"], report)

    shot_ids: list[str] = []
    dialogue_ids: set[str] = set()
    used_dialogue_ids: set[str] = set()
    used_shot_ids: set[str] = set()
    total = 0.0
    min_count, max_count = constraints.get("shot_count", [40, 60])
    min_dur, max_dur = constraints.get("shot_duration_sec", [3, 8])
    min_total, max_total = constraints.get("total_duration_sec", [170, 190])

    for index, row in enumerate(shots, start=2):
        where = f"{dir_path / 'shots.csv'}:{index}"
        shot_id = (row.get("shot_id") or "").strip()
        if not re.fullmatch(r"S\d{3}", shot_id):
            report.error(where, f"shot_id 非法: {shot_id!r}")
        if shot_id in used_shot_ids:
            report.error(where, f"shot_id 重复: {shot_id}")
        used_shot_ids.add(shot_id)
        shot_ids.append(shot_id)
        try:
            beat = int(row.get("beat", ""))
            if not 1 <= beat <= 5:
                raise ValueError
        except ValueError:
            report.error(where, f"beat 应为 1-5: {row.get('beat')!r}")
        try:
            duration = float(row.get("duration_sec", ""))
            if not min_dur <= duration <= max_dur:
                report.error(where, f"单镜时长 {duration:g}s 越界（{min_dur}-{max_dur}s）")
            total += duration
        except ValueError:
            report.error(where, f"duration_sec 不是数字: {row.get('duration_sec')!r}")
        prompt_file = (row.get("prompt_file") or "").strip()
        if not re.fullmatch(constraints.get("prompt_file_pattern", r"S\d{3}\.json"), prompt_file):
            report.error(where, f"prompt_file 非法: {prompt_file!r}")
        dialogue_id = (row.get("dialogue_id") or "").strip()
        if dialogue_id:
            used_dialogue_ids.add(dialogue_id)
        reference = (row.get("reference_shot") or "").strip()
        if reference and reference not in used_shot_ids:
            report.error(where, f"reference_shot 指向不存在或未来的镜头: {reference}")

    if not min_count <= len(shots) <= max_count:
        report.error(dir_path / "shots.csv", f"镜头数 {len(shots)}，期望 {min_count}-{max_count}")
    if not min_total <= total <= max_total:
        report.error(dir_path / "shots.csv", f"总时长 {total:g}s，期望 {min_total}-{max_total}s")

    for index, row in enumerate(dialogue, start=2):
        where = f"{dir_path / 'dialogue.csv'}:{index}"
        dialogue_id = (row.get("dialogue_id") or "").strip()
        if not dialogue_id:
            report.error(where, "dialogue_id 为空")
        if dialogue_id in dialogue_ids:
            report.error(where, f"dialogue_id 重复: {dialogue_id}")
        dialogue_ids.add(dialogue_id)
        if not nonempty_str(row.get("character")):
            report.error(where, "character 为空")
        if not nonempty_str(row.get("text")):
            report.error(where, "text 为空")

    missing = used_dialogue_ids - dialogue_ids
    if missing:
        report.error(dir_path / "shots.csv", f"引用了不存在的 dialogue_id: {sorted(missing)}")

    seen_cues = set()
    for index, row in enumerate(foley, start=2):
        where = f"{dir_path / 'foley.csv'}:{index}"
        cue_id = (row.get("cue_id") or "").strip()
        if not cue_id:
            report.error(where, "cue_id 为空")
        if cue_id in seen_cues:
            report.error(where, f"cue_id 重复: {cue_id}")
        seen_cues.add(cue_id)
        shot_id = (row.get("shot_id") or "").strip()
        if shot_id and shot_id not in used_shot_ids:
            report.error(where, f"shot_id 不存在: {shot_id}")


def validate_storyboard_file(path: Path, report: Report) -> None:
    """PostToolUse 单文件校验：不要求其余两表已存在。"""
    headers = load_schema("storyboard_headers.json")
    constraints = headers.get("constraints", {})
    stem = path.stem
    if stem not in ("shots", "dialogue", "foley"):
        report.error(path, f"未知分镜文件: {path.name}")
        return
    rows = read_csv(path, headers[stem], report)

    if stem == "shots":
        min_dur, max_dur = constraints.get("shot_duration_sec", [3, 8])
        min_count, max_count = constraints.get("shot_count", [40, 60])
        min_total, max_total = constraints.get("total_duration_sec", [170, 190])
        used_shot_ids: set[str] = set()
        used_dialogue_ids: set[str] = set()
        total = 0.0
        for index, row in enumerate(rows, start=2):
            where = f"{path}:{index}"
            shot_id = (row.get("shot_id") or "").strip()
            if not re.fullmatch(r"S\d{3}", shot_id):
                report.error(where, f"shot_id 非法: {shot_id!r}")
            if shot_id in used_shot_ids:
                report.error(where, f"shot_id 重复: {shot_id}")
            used_shot_ids.add(shot_id)
            try:
                beat = int(row.get("beat", ""))
                if not 1 <= beat <= 5:
                    raise ValueError
            except ValueError:
                report.error(where, f"beat 应为 1-5: {row.get('beat')!r}")
            try:
                duration = float(row.get("duration_sec", ""))
                if not min_dur <= duration <= max_dur:
                    report.error(where, f"单镜时长 {duration:g}s 越界（{min_dur}-{max_dur}s）")
                total += duration
            except ValueError:
                report.error(where, f"duration_sec 不是数字: {row.get('duration_sec')!r}")
            prompt_file = (row.get("prompt_file") or "").strip()
            if not re.fullmatch(constraints.get("prompt_file_pattern", r"S\d{3}\.json"), prompt_file):
                report.error(where, f"prompt_file 非法: {prompt_file!r}")
            dialogue_id = (row.get("dialogue_id") or "").strip()
            if dialogue_id:
                used_dialogue_ids.add(dialogue_id)
        if not min_count <= len(rows) <= max_count:
            report.error(path, f"镜头数 {len(rows)}，期望 {min_count}-{max_count}")
        if not min_total <= total <= max_total:
            report.error(path, f"总时长 {total:g}s，期望 {min_total}-{max_total}s")
        dialogue_path = path.parent / "dialogue.csv"
        if dialogue_path.exists():
            dialogue_rows = read_csv(dialogue_path, headers["dialogue"], report)
            known = {(row.get("dialogue_id") or "").strip() for row in dialogue_rows}
            missing = used_dialogue_ids - known
            if missing:
                report.error(path, f"引用了 dialogue.csv 中不存在的 dialogue_id: {sorted(missing)}")

    elif stem == "dialogue":
        seen: set[str] = set()
        for index, row in enumerate(rows, start=2):
            where = f"{path}:{index}"
            dialogue_id = (row.get("dialogue_id") or "").strip()
            if not dialogue_id:
                report.error(where, "dialogue_id 为空")
            if dialogue_id in seen:
                report.error(where, f"dialogue_id 重复: {dialogue_id}")
            seen.add(dialogue_id)
            if not nonempty_str(row.get("character")):
                report.error(where, "character 为空")
            if not nonempty_str(row.get("text")):
                report.error(where, "text 为空")

    else:  # foley
        seen_cues: set[str] = set()
        for index, row in enumerate(rows, start=2):
            where = f"{path}:{index}"
            cue_id = (row.get("cue_id") or "").strip()
            if not cue_id:
                report.error(where, "cue_id 为空")
            if cue_id in seen_cues:
                report.error(where, f"cue_id 重复: {cue_id}")
            seen_cues.add(cue_id)
            shot_id = (row.get("shot_id") or "").strip()
            if shot_id and not re.fullmatch(r"S\d{3}", shot_id):
                report.error(where, f"shot_id 格式非法: {shot_id!r}")


# ---------------------------------------------------------------- prompts


def validate_prompts(dir_path: Path, report: Report, require_any: bool = False) -> set[str]:
    if not dir_path.is_dir():
        report.error(dir_path, "目录不存在")
        return set()
    files = sorted(dir_path.glob("S*.json"))
    if require_any and not files:
        report.error(dir_path, "没有 S###.json 提示词")
    shot_ids: set[str] = set()
    for path in files:
        data, err = read_json(path)
        if err:
            report.error(path, f"JSON 解析失败: {err}")
            continue
        required = [
            "shot_id",
            "protagonist",
            "character_lock_ref",
            "character_lock_digest",
            "seed",
            "text2img",
            "img2video",
            "consistency",
        ]
        if not require(data, required, path, report):
            continue
        shot_id = str(data["shot_id"])
        if not re.fullmatch(r"S\d{3}", shot_id):
            report.error(path, f"shot_id 非法: {shot_id}")
        if shot_id != path.stem:
            report.error(path, f"shot_id {shot_id} 与文件名 {path.stem} 不一致")
        if shot_id in shot_ids:
            report.error(path, f"shot_id 重复: {shot_id}")
        shot_ids.add(shot_id)
        if data["protagonist"] not in PROTAGONISTS:
            report.error(path, f"protagonist 非法: {data['protagonist']}")
        if not is_int(data["seed"]):
            report.error(path, "seed 应为整数")
        lock_path = resolve_project_path(str(data["character_lock_ref"]))
        if not lock_path.exists():
            report.error(path, f"character_lock_ref 指向不存在的文件: {data['character_lock_ref']}")
        if not nonempty_str(data["character_lock_digest"]):
            report.error(path, "character_lock_digest 为空")

        text2img = data["text2img"]
        if require(text2img, ["prompt", "negative_prompt", "params"], path, report):
            if len(str(text2img["prompt"]).strip()) < 10:
                report.error(path, "text2img.prompt 过短")
            if not nonempty_str(text2img["negative_prompt"]):
                report.error(path, "text2img.negative_prompt 为空")

        img2video = data["img2video"]
        if require(img2video, ["prompt", "first_frame", "last_frame", "params"], path, report):
            if len(str(img2video["prompt"]).strip()) < 10:
                report.error(path, "img2video.prompt 过短")

        consistency = data["consistency"]
        if require(consistency, ["method", "reference_image"], path, report):
            method = consistency["method"]
            if method not in {"text2img", "img2img"}:
                report.error(path, f"consistency.method 非法: {method}")
            if shot_id == "S001" and method != "text2img":
                report.error(path, "首镜 S001 必须用 text2img 定标")
            if shot_id != "S001" and method != "img2img":
                report.warn(path, f"{shot_id} 建议用 img2img 以保住主角一致性")
    return shot_ids


# ---------------------------------------------------------------- gate / all


def find_episode_file(episode: str, report: Report) -> Path | None:
    files = sorted((ROOT / "02_script" / "episodes").glob(f"{episode}_*.json"))
    if not files:
        report.error(ROOT / "02_script" / "episodes", f"找不到 {episode}_*.json")
        return None
    if len(files) > 1:
        report.error(ROOT / "02_script" / "episodes", f"{episode} 有多个剧本文件: {[p.name for p in files]}")
        return None
    return files[0]


def validate_gate(episode: str, report: Report) -> None:
    episode_path = find_episode_file(episode, report)
    if episode_path is None:
        return
    data = validate_episode(episode_path, report)
    storyboard_dir = ROOT / "03_storyboard" / episode
    prompts_dir = ROOT / "04_prompts" / episode
    validate_storyboard(storyboard_dir, report)
    prompt_ids = validate_prompts(prompts_dir, report, require_any=True)

    if data is not None:
        protagonist_path = ROOT / "04_prompts" / "_shared" / "protagonist.json"
        selected = None
        if protagonist_path.exists():
            selected_data, err = read_json(protagonist_path)
            if err:
                report.error(protagonist_path, f"JSON 解析失败: {err}")
            else:
                selected = selected_data.get("selected")
        if selected and selected != "undecided":
            if data.get("protagonist") != selected:
                report.error(episode_path, f"主角已定选 {selected}，剧本写的是 {data.get('protagonist')}")
        elif data.get("protagonist") not in (None, "undecided"):
            report.warn(episode_path, "主角尚未定选，剧本应保持 undecided")

    shots_path = storyboard_dir / "shots.csv"
    if shots_path.exists():
        headers = load_schema("storyboard_headers.json")
        shots = read_csv(shots_path, headers["shots"], report)
        shot_ids = {(row.get("shot_id") or "").strip() for row in shots}
        if shot_ids and prompt_ids and shot_ids != prompt_ids:
            missing_prompts = sorted(shot_ids - prompt_ids)
            orphan_prompts = sorted(prompt_ids - shot_ids)
            if missing_prompts:
                report.error(prompts_dir, f"缺提示词的镜头: {missing_prompts}")
            if orphan_prompts:
                report.error(prompts_dir, f"分镜表中不存在的提示词: {orphan_prompts}")


def validate_all(report: Report) -> int:
    count = 0
    for path in sorted((ROOT / "02_script" / "episodes").glob("EP*.json")):
        validate_episode(path, report)
        count += 1
    for path in sorted((ROOT / "03_storyboard").glob("EP*")):
        if path.is_dir():
            validate_storyboard(path, report)
            count += 1
    for path in sorted((ROOT / "04_prompts").glob("EP*")):
        if path.is_dir():
            validate_prompts(path, report)
            count += 1
    lock_path = ROOT / "04_prompts" / "_shared" / "character_lock.json"
    if lock_path.exists():
        validate_character_lock(lock_path, report)
    if count == 0:
        print("[validate] all: 0 artifacts")
    return count


# ---------------------------------------------------------------- docs


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip("\n").splitlines()
    data: dict = {}
    current_key = None
    for line in block:
        if not line.strip():
            continue
        if line.startswith(("  - ", "- ")):
            if current_key:
                data.setdefault(current_key, [])
                if isinstance(data[current_key], list):
                    data[current_key].append(line.split("- ", 1)[1].strip())
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            data[key] = value if value else []
    return data


def validate_docs(report: Report) -> None:
    required = ["CLAUDE.md", "README.md", "TODO.md", "KNOWN_ISSUES.md"]
    for name in required:
        path = ROOT / name
        if not path.exists():
            report.error(path, "文件不存在")

    claude_path = ROOT / "CLAUDE.md"
    if claude_path.exists():
        text = claude_path.read_text(encoding="utf-8")
        if "├──" in text or "└──" in text:
            report.error(claude_path, "CLAUDE.md 不得包含目录树，目录树归 README §1")
        for section in ("## §1", "## §2", "## §3", "## §4", "## §5"):
            if section not in text:
                report.error(claude_path, f"缺章节 {section}")

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
        if "## 1." not in text:
            report.error(readme_path, "缺「## 1. 项目结构」章节")

    issues_path = ROOT / "KNOWN_ISSUES.md"
    if issues_path.exists():
        text = issues_path.read_text(encoding="utf-8")
        for column in ("编号", "现象", "影响", "触发条件", "临时规避", "状态"):
            if column not in text:
                report.error(issues_path, f"缺列 {column}")

    settings_path = ROOT / ".claude" / "settings.json"
    if settings_path.exists():
        data, err = read_json(settings_path)
        if err:
            report.error(settings_path, f"JSON 解析失败: {err}")
        elif "hooks" not in (data or {}):
            report.error(settings_path, "缺 hooks 配置")
    else:
        report.error(settings_path, "文件不存在")

    for name in AGENT_NAMES:
        path = ROOT / ".claude" / "agents" / f"{name}.md"
        if not path.exists():
            report.error(path, "代理卡不存在")
            continue
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("name") != name:
            report.error(path, f"frontmatter name 应为 {name}，实际 {meta.get('name')!r}")
        if not meta.get("description"):
            report.error(path, "frontmatter 缺 description")
        tools = meta.get("tools", [])
        tools_text = " ".join(tools) if isinstance(tools, list) else str(tools)
        if "Agent" in tools_text:
            report.error(path, "tools 不得包含 Agent（结构性约束）")
        memory = ROOT / ".claude" / "agents" / "agent-memory" / name / "MEMORY.md"
        if not memory.exists():
            report.error(memory, "记忆索引不存在")

    for name in SKILL_NAMES:
        path = ROOT / ".claude" / "skills" / name / "SKILL.md"
        if not path.exists():
            report.error(path, "SKILL.md 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        if meta.get("name") != name:
            report.error(path, f"frontmatter name 应为 {name}，实际 {meta.get('name')!r}")
        if "## 禁止" not in text:
            report.error(path, "缺「## 禁止」章节")

    lock_path = ROOT / "04_prompts" / "_shared" / "character_lock.json"
    if lock_path.exists():
        validate_character_lock(lock_path, report)
    else:
        report.error(lock_path, "角色锁不存在")

    validate_schemas(report)


# ---------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="《五境试炼》产物校验器")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="校验 00_schema 自身")
    lock = sub.add_parser("lock", help="校验角色锁与主角选择一致性")
    lock.add_argument("path", nargs="?", default=None)
    sub.add_parser("docs", help="校验配置文档、代理、skill、settings")
    sub.add_parser("all", help="扫描并校验现有全部产物")
    episode = sub.add_parser("episode", help="校验单集剧本")
    episode.add_argument("path")
    storyboard = sub.add_parser("storyboard", help="校验分镜三表")
    storyboard.add_argument("path")
    storyboard_file = sub.add_parser("storyboard-file", help="校验单张分镜 CSV")
    storyboard_file.add_argument("path")
    prompts = sub.add_parser("prompts", help="校验提示词包")
    prompts.add_argument("path")
    gate = sub.add_parser("gate", help="单集总门禁")
    gate.add_argument("episode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = Report(args.command)
    if args.command == "schema":
        validate_schemas(report)
    elif args.command == "lock":
        lock_path = Path(args.path) if args.path else ROOT / "04_prompts" / "_shared" / "character_lock.json"
        validate_character_lock(lock_path, report)
    elif args.command == "docs":
        validate_docs(report)
    elif args.command == "all":
        validate_all(report)
    elif args.command == "episode":
        validate_episode(Path(args.path), report)
    elif args.command == "storyboard":
        validate_storyboard(Path(args.path), report)
    elif args.command == "storyboard-file":
        validate_storyboard_file(Path(args.path), report)
    elif args.command == "prompts":
        validate_prompts(Path(args.path), report)
    elif args.command == "gate":
        validate_gate(args.episode, report)
    return 0 if report.emit() else 1


if __name__ == "__main__":
    raise SystemExit(main())
