"""L2 剧本层：生成单集 JSON、校验并回灌修复。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import config as config_module
import jsonutil
import llm
import state
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
PROMPT_PATH = config_module.PIPELINE_DIR / "prompts" / "L2.md"
SCHEMA_PATH = PROJECT_ROOT / "00_schema" / "episode.schema.json"
STRUCTURED_PATH = PROJECT_ROOT / "01_data" / "structured" / "computer.json"
WORLD_BIBLE = PROJECT_ROOT / "02_script" / "world_bible.md"
CHARACTER_BIBLE = PROJECT_ROOT / "02_script" / "character_bible.md"
PROTAGONIST_PATH = PROJECT_ROOT / "04_prompts" / "_shared" / "protagonist.json"
OUTPUT_DIR = PROJECT_ROOT / "02_script" / "episodes"
VALIDATOR = PROJECT_ROOT / ".claude" / "scripts" / "validate.py"

REQUIRED_FIELDS = [
    "episode_id",
    "major",
    "major_en",
    "realm",
    "protagonist",
    "logline",
    "beats",
    "knowledge_points",
    "characters",
    "next_episode_hook",
    "continuity",
    "sources",
]
V2_FIELDS = ("coverage",)
# version 2 专业解说固定四段时轴（用户批准：210 秒）
V2_BEATS = (
    (1, "开场", 0, 18),
    (2, "课程", 18, 118),
    (3, "就业", 118, 198),
    (4, "收束", 198, 210),
)
FORBIDDEN_NAMES = ("烈", "镜")
ALL_REALMS = ("修仙境", "机枢城", "万象医馆", "星渊观测所", "言灵殿")


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def expected_coverage() -> dict[str, list[str]]:
    """从已批准的 L1 数据读取必须出现的课程/就业名单。"""
    structured = json.loads(STRUCTURED_PATH.read_text(encoding="utf-8"))
    return {
        "courses": [item["name"] for item in structured["courses"]],
        "employment": [item["name"] for item in structured["employment"]["directions"]],
    }


def _validate_coverage(coverage) -> list[str]:
    errors: list[str] = []
    if not isinstance(coverage, dict):
        return ["coverage 必须是对象"]
    for key, minimum in (("courses", 5), ("employment", 5)):
        values = coverage.get(key)
        if not isinstance(values, list) or len(values) < minimum:
            errors.append(f"coverage.{key} 至少 {minimum} 条")
            continue
        if not all(isinstance(item, str) and item.strip() for item in values):
            errors.append(f"coverage.{key} 含空值")
    return errors


def validate_l2(
    data,
    expected_episode: str = "EP01",
    expected_major_en: str = "computer",
    expected_realm: str = "修仙境",
    expected_protagonist: str = "undecided",
    expected_coverage_data: dict[str, list[str]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象"]
    version = data.get("version", 1)
    is_v2 = _is_int(version) and version >= 2
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if is_v2:
        missing += [field for field in V2_FIELDS if field not in data]
    if missing:
        errors.append("缺少字段: " + ", ".join(missing))
        return errors
    if "mentors" in data or "mentor_portrait" in data:
        errors.append("v2 剧本不得包含导师字段 mentors/mentor_portrait")

    if data["episode_id"] != expected_episode:
        errors.append(f"episode_id 应为 {expected_episode}")
    if data["major_en"] != expected_major_en:
        errors.append(f"major_en 应为 {expected_major_en}")
    if data["realm"] != expected_realm:
        errors.append(f"realm 应为 {expected_realm}")
    if data["protagonist"] != expected_protagonist:
        errors.append(f"protagonist 应为 {expected_protagonist}")
    if not isinstance(data["logline"], str) or len(data["logline"]) < 10:
        errors.append("logline 至少 10 字")

    beats = data["beats"]
    if not isinstance(beats, list) or len(beats) != 4:
        errors.append("beats 必须为 4 段")
    else:
        total = 0.0
        indices = set()
        for beat in beats:
            if not isinstance(beat, dict):
                errors.append("beats 含非对象")
                continue
            for field in ("index", "name", "start_sec", "end_sec", "summary"):
                if field not in beat:
                    errors.append(f"beat 缺少 {field}")
            if not _is_int(beat.get("index")) or not 1 <= beat["index"] <= 4:
                errors.append(f"beat index 非法: {beat.get('index')!r}")
            else:
                indices.add(beat["index"])
            if not _is_num(beat.get("start_sec")) or not _is_num(beat.get("end_sec")):
                errors.append(f"beat {beat.get('index')} 时间不是数字")
                continue
            if beat["end_sec"] <= beat["start_sec"]:
                errors.append(f"beat {beat.get('index')} 结束时间必须大于开始时间")
            total += beat["end_sec"] - beat["start_sec"]
        if indices != {1, 2, 3, 4}:
            errors.append(f"beat index 必须覆盖 1-4，实际 {sorted(indices)}")
        if not 200 <= total <= 220:
            errors.append(f"beats 总时长 {total:g}s 越界（200-220s）")
        if is_v2:
            for beat, (exp_index, exp_name, exp_start, exp_end) in zip(beats, V2_BEATS):
                if not isinstance(beat, dict):
                    continue
                if beat.get("index") != exp_index or beat.get("name") != exp_name:
                    errors.append(
                        f"v2 beat {exp_index} 名称应为「{exp_name}」，实际 "
                        f"{beat.get('index')!r}/「{beat.get('name')}」"
                    )
                if beat.get("start_sec") != exp_start or beat.get("end_sec") != exp_end:
                    errors.append(
                        f"v2 beat {exp_index} 时轴应为 {exp_start}-{exp_end}s，实际 "
                        f"{beat.get('start_sec')}-{beat.get('end_sec')}s"
                    )

    points = data["knowledge_points"]
    if not isinstance(points, list) or len(points) < 3:
        errors.append("knowledge_points 至少 3 条")
    else:
        for point in points:
            if not isinstance(point, dict):
                errors.append("knowledge_points 含非对象")
                continue
            for field in ("id", "title", "explain", "misconception", "source_ref"):
                if not point.get(field):
                    errors.append(f"知识点 {point.get('id')!r} 缺 {field}")

    characters = data["characters"]
    if not isinstance(characters, list) or not characters:
        errors.append("characters 至少 1 个")

    if is_v2:
        errors.extend(_validate_coverage(data.get("coverage")))
        if expected_coverage_data is not None:
            for key in ("courses", "employment"):
                actual = [str(item).strip() for item in (data.get("coverage") or {}).get(key, [])]
                expected = list(expected_coverage_data.get(key, []))
                if actual != expected:
                    errors.append(f"coverage.{key} 必须与 L1 数据完全一致")

    continuity = data["continuity"]
    if not isinstance(continuity, dict) or not isinstance(continuity.get("open_threads"), list):
        errors.append("continuity.open_threads 必须为数组")
    elif expected_episode == "EP01":
        prev_summary = str(continuity.get("prev_summary", ""))
        if "首集" not in prev_summary and "无上集" not in prev_summary:
            errors.append("EP01 的 continuity.prev_summary 必须写「首集/无上集」，不得编造上集")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        errors.append("sources 至少 1 条")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"sources[{index}] 不是对象")
                continue
            url = source.get("url")
            if not isinstance(url, str) or not url.startswith("http"):
                errors.append(f"sources[{index}] 缺有效 URL")
            if not isinstance(source.get("retrieved_at"), str) or not source["retrieved_at"]:
                errors.append(f"sources[{index}] 缺 retrieved_at")
            if not _is_int(source.get("year")) or not 2000 <= source["year"] <= 2030:
                errors.append(f"sources[{index}] year 必须为 2000-2030 整数")

    if not isinstance(data["next_episode_hook"], str) or not data["next_episode_hook"].strip():
        errors.append("next_episode_hook 为空")
    else:
        for realm in ALL_REALMS:
            if realm != data["realm"] and realm in data["next_episode_hook"]:
                errors.append(f"next_episode_hook 不得跳到其它境「{realm}」")

    text = json.dumps(data, ensure_ascii=False)
    for name in FORBIDDEN_NAMES:
        if name in text:
            errors.append(f"剧本不得出现主角名「{name}」，统一写「试炼者」")
    if "试炼者" not in text:
        errors.append("主角必须统一写「试炼者」")
    return errors


def _selected_protagonist() -> str:
    try:
        data = json.loads(PROTAGONIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "undecided"
    selected = data.get("selected")
    return selected if selected in ("lie", "mirror") else "undecided"


def _load_inputs() -> dict[str, str]:
    required = {
        "structured": STRUCTURED_PATH,
        "world_bible": WORLD_BIBLE,
        "character_bible": CHARACTER_BIBLE,
        "protagonist": PROTAGONIST_PATH,
        "schema": SCHEMA_PATH,
        "prompt": PROMPT_PATH,
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise PipelineError("L2 缺少输入文件: " + ", ".join(missing), code=4)
    return {key: path.read_text(encoding="utf-8") for key, path in required.items()}


def _messages(inputs: dict[str, str]) -> list[dict]:
    system = (
        inputs["prompt"]
        + "\n\n## episode.schema.json\n"
        + inputs["schema"]
        + "\n\n只返回一个单集 JSON 对象，不要 Markdown 围栏或解释。"
        + "主角统一写「试炼者」；不再写任何导师或导师画像。"
        + "version 必须写 2，并输出 coverage。"
    )
    user = (
        "## 01_data/structured/computer.json\n"
        + inputs["structured"]
        + "\n\n## 02_script/world_bible.md\n"
        + inputs["world_bible"]
        + "\n\n## 02_script/character_bible.md\n"
        + inputs["character_bible"]
        + "\n\n## 04_prompts/_shared/protagonist.json\n"
        + inputs["protagonist"]
        + "\n\n请按要求只返回 JSON。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _run_validator(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "episode", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def _summary(data: dict, path: Path) -> dict:
    return {
        "episode_id": data.get("episode_id"),
        "logline": data.get("logline"),
        "durations": [beat.get("end_sec", 0) - beat.get("start_sec", 0) for beat in data["beats"]],
        "knowledge_points": [point.get("title") for point in data["knowledge_points"]],
        "coverage": data.get("coverage"),
        "sources": len(data.get("sources") or []),
        "path": str(path),
    }


def run(
    episode: str = "EP01",
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    if episode != "EP01":
        raise PipelineError("Phase 1 仅支持 EP01", code=4)
    output_path = OUTPUT_DIR / "EP01_computer.json"
    if resume and output_path.is_file():
        passed, output = _run_validator(output_path)
        if not passed:
            raise PipelineError("L2 resume 未通过 validate.py episode: " + output)
        data = json.loads(output_path.read_text(encoding="utf-8"))
        if int(data.get("version", 1)) < 2:
            raise PipelineError("L2 旧版剧本缺少课程/就业覆盖，请去掉 --resume 重新生成", code=7)
        errors = validate_l2(
            data,
            episode,
            "computer",
            expected_protagonist=_selected_protagonist(),
            expected_coverage_data=expected_coverage(),
        )
        if errors:
            raise PipelineError("L2 resume 校验失败：" + "; ".join(errors))
        return _summary(data, output_path)

    inputs = _load_inputs()
    messages = _messages(inputs)
    candidate = OUTPUT_DIR / ".EP01_computer.candidate.json"
    errors: list[str] = []
    data = None
    try:
        for attempt in range(3):
            result = llm.chat(
                "L2",
                messages,
                max_tokens=8192,
                response_format="json_object",
                config=config_obj,
                episode=episode,
            )
            try:
                data = jsonutil.extract_json(result["content"])
            except ValueError as exc:
                errors = [str(exc)]
            else:
                errors = validate_l2(
                    data,
                    episode,
                    "computer",
                    expected_protagonist=_selected_protagonist(),
                    expected_coverage_data=expected_coverage(),
                )
                if not errors:
                    state.write_json(candidate, data)
                    passed, output = _run_validator(candidate)
                    if passed:
                        state.write_json(output_path, data)
                        return _summary(data, output_path)
                    errors = ["validate.py episode 未通过:\n" + output]
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
        if candidate.exists():
            candidate.unlink()
    raise PipelineError("L2 校验重试耗尽：" + "; ".join(errors))
