"""L4 提示词层：读分镜与角色锁，分批生成单镜提示词包。"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import config as config_module
import jsonutil
import llm
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
PROMPT_PATH = config_module.PIPELINE_DIR / "prompts" / "L4.md"
SCHEMA_PATH = PROJECT_ROOT / "00_schema" / "shot_prompt.schema.json"
TEMPLATES_DIR = PROJECT_ROOT / "04_prompts" / "_shared" / "templates"
SHOTS_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "shots.csv"
LOCK_PATH = PROJECT_ROOT / "04_prompts" / "_shared" / "character_lock.json"
PROTAGONIST_PATH = PROJECT_ROOT / "04_prompts" / "_shared" / "protagonist.json"
OUTPUT_DIR = PROJECT_ROOT / "04_prompts" / "EP01"
VALIDATOR = PROJECT_ROOT / ".claude" / "scripts" / "validate.py"

LOCK_REF = "04_prompts/_shared/character_lock.json"
REFERENCE_S001 = "05_assets/characters/lie_ref_v1.png"
DEFAULT_NEGATIVE = (
    "blurry, lowres, jpeg artifacts, extra fingers, extra limbs, deformed hands, "
    "text, watermark, signature, photorealistic, 3d render"
)
REQUIRED_FIELDS = (
    "shot_id",
    "protagonist",
    "character_lock_ref",
    "character_lock_digest",
    "seed",
    "text2img",
    "img2video",
    "consistency",
)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def canonical_digest(obj) -> str:
    """与 .claude/hooks/_hooklib.canonical_digest 保持同一算法。"""
    canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_context() -> tuple[dict, str, str, list[dict], dict]:
    for path in (PROMPT_PATH, SCHEMA_PATH, SHOTS_PATH, LOCK_PATH, PROTAGONIST_PATH):
        if not path.is_file():
            raise PipelineError(f"L4 缺少输入文件: {path}", code=4)
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    protagonist = json.loads(PROTAGONIST_PATH.read_text(encoding="utf-8"))
    selected = protagonist.get("selected", "undecided")
    if selected not in ("lie", "mirror"):
        raise PipelineError("G2-ROLE 未完成：protagonist.selected 不是 lie/mirror", code=3)
    shots = list(csv.DictReader(SHOTS_PATH.open(encoding="utf-8")))
    if not shots:
        raise PipelineError("L4 分镜表为空", code=4)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    templates = "\n\n".join(
        path.read_text(encoding="utf-8") for path in sorted(TEMPLATES_DIR.glob("*.md"))
    )
    return lock, selected, prompt, shots, {"schema": schema, "templates": templates}


def _normalize(item, shot: dict, selected: str, lock: dict, digest: str) -> dict:
    shot_id = shot["shot_id"]
    character = lock["protagonists"][selected]
    prefix = character["prompt_prefix"]
    seed_start, seed_end = character["seed_range"]

    data = dict(item) if isinstance(item, dict) else {}
    text2img = dict(data.get("text2img") or {}) if isinstance(data.get("text2img"), dict) else {}
    img2video = dict(data.get("img2video") or {}) if isinstance(data.get("img2video"), dict) else {}

    prompt = str(text2img.get("prompt") or "").strip()
    if not prompt:
        prompt = (
            f"{shot.get('action', '')}，{shot.get('scene', '')}，"
            f"{shot.get('shot_size', '')}，{shot.get('camera_move', '')}，2D anime cel shading"
        )
    if prefix not in prompt:
        prompt = f"{prefix}, {prompt}"
    text2img["prompt"] = prompt
    text2img["negative_prompt"] = str(text2img.get("negative_prompt") or "").strip() or DEFAULT_NEGATIVE
    params = text2img.get("params") if isinstance(text2img.get("params"), dict) else {}
    params["width"] = 1920
    params["height"] = 1080
    text2img["params"] = params

    video_prompt = str(img2video.get("prompt") or "").strip()
    if len(video_prompt) < 10:
        video_prompt = f"{shot.get('action', '')}，运镜：{shot.get('camera_move', '固定')}，保持角色外观一致"
    img2video["prompt"] = video_prompt
    img2video["first_frame"] = (
        f"06_render/keyframes/EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.png"
    )
    img2video["last_frame"] = str(img2video.get("last_frame") or "")
    video_params = img2video.get("params") if isinstance(img2video.get("params"), dict) else {}
    video_params["duration_sec"] = float(shot["duration_sec"])
    img2video["params"] = video_params

    seed = data.get("seed")
    if not _is_int(seed) or not seed_start <= seed <= seed_end:
        seed = seed_start + (int(shot_id[1:]) - 1) % (seed_end - seed_start + 1)

    method = "text2img" if shot_id == "S001" else "img2img"
    reference = "" if shot_id == "S001" else REFERENCE_S001
    return {
        "shot_id": shot_id,
        "protagonist": selected,
        "character_lock_ref": LOCK_REF,
        "character_lock_digest": digest,
        "seed": seed,
        "text2img": text2img,
        "img2video": img2video,
        "consistency": {"method": method, "reference_image": reference},
        "notes": str(data.get("notes") or f"L4 生成，分镜 beat {shot.get('beat', '')}"),
    }


def validate_prompt(data, shot: dict, selected: str, lock: dict, digest: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["提示词包必须是对象"]
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        return ["缺少字段: " + ", ".join(missing)]
    shot_id = shot["shot_id"]
    if data["shot_id"] != shot_id:
        errors.append(f"shot_id 应为 {shot_id}")
    if data["protagonist"] != selected:
        errors.append(f"protagonist 应为 {selected}")
    if data["character_lock_ref"] != LOCK_REF:
        errors.append("character_lock_ref 不正确")
    if data["character_lock_digest"] != digest:
        errors.append("character_lock_digest 与当前角色锁不一致")
    seed = data.get("seed")
    seed_range = lock["protagonists"][selected]["seed_range"]
    if not _is_int(seed) or not seed_range or not seed_range[0] <= seed <= seed_range[1]:
        errors.append("seed 必须是角色锁区间内的整数")
    prefix = lock["protagonists"][selected]["prompt_prefix"]
    text2img = data.get("text2img")
    if not isinstance(text2img, dict):
        errors.append("text2img 必须是对象")
    else:
        prompt = str(text2img.get("prompt") or "")
        if len(prompt) < 10:
            errors.append("text2img.prompt 过短")
        if prefix not in prompt:
            errors.append("text2img.prompt 必须包含角色锁 prompt_prefix")
        if not str(text2img.get("negative_prompt") or "").strip():
            errors.append("text2img.negative_prompt 为空")
        if not isinstance(text2img.get("params"), dict):
            errors.append("text2img.params 必须是对象")
    img2video = data.get("img2video")
    if not isinstance(img2video, dict):
        errors.append("img2video 必须是对象")
    else:
        if len(str(img2video.get("prompt") or "")) < 10:
            errors.append("img2video.prompt 过短")
        if f"EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.png" not in str(
            img2video.get("first_frame") or ""
        ):
            errors.append("img2video.first_frame 必须指向本镜关键帧")
        if not isinstance(img2video.get("params"), dict):
            errors.append("img2video.params 必须是对象")
    consistency = data.get("consistency")
    if not isinstance(consistency, dict):
        errors.append("consistency 必须是对象")
    else:
        expected_method = "text2img" if shot_id == "S001" else "img2img"
        if consistency.get("method") != expected_method:
            errors.append(f"consistency.method 应为 {expected_method}")
        expected_ref = "" if shot_id == "S001" else REFERENCE_S001
        if consistency.get("reference_image") != expected_ref:
            errors.append("consistency.reference_image 不正确")
    return errors


def _messages(
    prompt: str,
    schema: str,
    templates: str,
    lock: dict,
    selected: str,
    digest: str,
    batch: list[dict],
) -> list[dict]:
    system = (
        prompt
        + "\n\n## shot_prompt.schema.json\n"
        + schema
        + "\n\n## 模板\n"
        + templates
        + "\n\n## 角色锁\n"
        + json.dumps(lock, ensure_ascii=False, indent=2)
        + f"\n\n## 已定选主角\n{selected}\n固定 digest：{digest}\n"
        + "只返回 JSON 对象：{\"prompts\": [...]}，每镜一个对象，数量必须与本批镜头数一致。"
        + "不要 Markdown 围栏或解释。"
    )
    user = (
        "## 本批分镜\n"
        + json.dumps(batch, ensure_ascii=False, indent=2)
        + "\n\n请按 shot_id 逐镜生成提示词包，只返回 JSON。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _run_validator(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "prompts", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def _extract_prompts(content: str) -> list[dict]:
    payload = jsonutil.extract_json(content)
    if isinstance(payload, dict) and isinstance(payload.get("prompts"), list):
        return payload["prompts"]
    if isinstance(payload, list):
        return payload
    raise ValueError("模型未返回 prompts 数组")


def _write_prompt(data: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{data['shot_id']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _summary(selected: str, digest: str) -> dict:
    files = sorted(OUTPUT_DIR.glob("S*.json"))
    return {
        "prompts": len(files),
        "protagonist": selected,
        "character_lock_digest": digest,
        "path": str(OUTPUT_DIR),
    }


def refresh_lock() -> dict:
    """角色锁变更后，重写全部提示词包的 digest 与参考图字段。"""
    lock, selected, _prompt, shots, _extra = load_context()
    digest = canonical_digest(lock)
    shot_by_id = {shot["shot_id"]: shot for shot in shots}
    updated = 0
    for path in sorted(OUTPUT_DIR.glob("S*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        shot = shot_by_id.get(str(data.get("shot_id", "")))
        if shot is None:
            continue
        normalized = _normalize(data, shot, selected, lock, digest)
        errors = validate_prompt(normalized, shot, selected, lock, digest)
        if errors:
            raise PipelineError(f"{path.name} 刷新后校验失败: " + "; ".join(errors))
        _write_prompt(normalized)
        updated += 1
    passed, output = _run_validator(OUTPUT_DIR)
    if not passed:
        raise PipelineError("L4 刷新后未通过 validate.py prompts: " + output)
    return {"updated": updated, "digest": digest, "protagonist": selected}


def run(
    episode: str = "EP01",
    batch: int = 4,
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    if episode != "EP01":
        raise PipelineError("Phase 2 仅支持 EP01", code=4)
    if batch < 1 or batch > 20:
        raise PipelineError("--batch 必须在 1-20 之间", code=4)

    lock, selected, prompt, shots, extra = load_context()
    digest = canonical_digest(lock)
    shot_by_id = {shot["shot_id"]: shot for shot in shots}
    existing: dict[str, dict] = {}
    if resume and OUTPUT_DIR.is_dir():
        for path in sorted(OUTPUT_DIR.glob("S*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            shot = shot_by_id.get(str(data.get("shot_id", "")))
            if shot is not None and not validate_prompt(data, shot, selected, lock, digest):
                existing[data["shot_id"]] = data

    missing = [shot for shot in shots if shot["shot_id"] not in existing]
    if not missing:
        passed, output = _run_validator(OUTPUT_DIR)
        if not passed:
            raise PipelineError("L4 resume 未通过 validate.py prompts: " + output)
        return _summary(selected, digest)

    errors: list[str] = []
    for start in range(0, len(missing), batch):
        chunk = missing[start : start + batch]
        messages = _messages(
            prompt,
            extra["schema"],
            extra["templates"],
            lock,
            selected,
            digest,
            chunk,
        )
        completed: dict[str, dict] = {}
        for attempt in range(3):
            result = llm.chat(
                "L4",
                messages,
                max_tokens=32768,
                response_format="json_object",
                timeout=300,
                config=config_obj,
                episode=episode,
            )
            try:
                items = _extract_prompts(result["content"])
            except ValueError as exc:
                errors = [str(exc)]
            else:
                by_id = {
                    str(item.get("shot_id")): item
                    for item in items
                    if isinstance(item, dict) and item.get("shot_id")
                }
                problems: list[str] = []
                for shot in chunk:
                    shot_id = shot["shot_id"]
                    if shot_id not in by_id:
                        problems.append(f"缺少 {shot_id}")
                        continue
                    normalized = _normalize(by_id[shot_id], shot, selected, lock, digest)
                    current = validate_prompt(normalized, shot, selected, lock, digest)
                    if current:
                        problems.extend(f"{shot_id}: {item}" for item in current)
                    else:
                        completed[shot_id] = normalized
                if not problems:
                    for shot_id in [shot["shot_id"] for shot in chunk]:
                        _write_prompt(completed[shot_id])
                    errors = []
                    break
                errors = problems
            if attempt < 2:
                messages = messages + [
                    {"role": "assistant", "content": result["content"]},
                    {
                        "role": "user",
                        "content": "上次输出未通过校验，请只返回修复后的完整 JSON。错误：\n- "
                        + "\n- ".join(errors),
                    },
                ]
        if errors:
            raise PipelineError("L4 分批校验重试耗尽：" + "; ".join(errors))

    passed, output = _run_validator(OUTPUT_DIR)
    if not passed:
        raise PipelineError("L4 未通过 validate.py prompts: " + output)
    return _summary(selected, digest)
