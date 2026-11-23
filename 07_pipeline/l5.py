"""L5 媒体编排：关键帧生成与 manifest。"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import config as config_module
import media_image
import media_tts
import media_video
import state
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
PROMPTS_DIR = PROJECT_ROOT / "04_prompts" / "EP01"
KEYFRAME_DIR = PROJECT_ROOT / "06_render" / "keyframes"
MANIFEST_PATH = PROJECT_ROOT / "06_render" / "EP01" / "keyframes_manifest.json"
VIDEO_DIR = PROJECT_ROOT / "06_render" / "videos"
VIDEO_MANIFEST_PATH = PROJECT_ROOT / "06_render" / "EP01" / "videos_manifest.json"
AUDIO_DIR = PROJECT_ROOT / "05_assets" / "audio"
TTS_MANIFEST_PATH = PROJECT_ROOT / "05_assets" / "audio" / "EP01_tts_manifest.json"
SHOTS_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "shots.csv"
DIALOGUE_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "dialogue.csv"
PROTAGONIST_PATH = PROJECT_ROOT / "04_prompts" / "_shared" / "protagonist.json"
S001 = "S001"
REFERENCE_CHARACTER = PROJECT_ROOT / "05_assets" / "characters" / "lie_ref_v1.png"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_prompt(shot_id: str) -> dict:
    path = PROMPTS_DIR / f"{shot_id}.json"
    if not path.is_file():
        raise PipelineError(f"缺少提示词包: {path}", code=4)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest() -> dict:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"episode": "EP01", "shots": {}}


def _selected_shots(raw: str | None) -> list[str]:
    if not raw:
        files = sorted(PROMPTS_DIR.glob("S*.json"))
        if not files:
            raise PipelineError("没有可用的提示词包", code=4)
        return [path.stem for path in files]
    shots = [item.strip() for item in raw.split(",") if item.strip()]
    for shot_id in shots:
        if not (len(shot_id) == 4 and shot_id[0] == "S" and shot_id[1:].isdigit()):
            raise PipelineError(f"非法 shot_id: {shot_id}", code=4)
    return shots


def _load_manifest_at(path: Path, episode: str = "EP01") -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"episode": episode, "shots": {}}


def _write_manifest(path: Path, data: dict) -> None:
    state.write_json(path, data)


def _parse_shot_ids(raw: str | None, default_dir: Path) -> list[str]:
    if not raw:
        files = sorted(default_dir.glob("S*.json"))
        if not files:
            raise PipelineError("没有可用的提示词包", code=4)
        return [path.stem for path in files]
    shots = [item.strip() for item in raw.split(",") if item.strip()]
    for shot_id in shots:
        if not (len(shot_id) == 4 and shot_id[0] == "S" and shot_id[1:].isdigit()):
            raise PipelineError(f"非法 shot_id: {shot_id}", code=4)
    return shots


def _shot_map() -> dict[str, dict]:
    with SHOTS_PATH.open(encoding="utf-8") as handle:
        return {row["shot_id"]: row for row in csv.DictReader(handle)}


def keyframes(
    shots_raw: str | None = None,
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    shots = _selected_shots(shots_raw)
    manifest = _load_manifest()
    done = 0
    failed: list[dict] = []
    for shot_id in shots:
        prompt_data = _load_prompt(shot_id)
        output_path = KEYFRAME_DIR / f"EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.png"
        entry = manifest["shots"].get(shot_id, {})
        if resume and output_path.is_file() and output_path.stat().st_size > 0:
            entry.update(
                {
                    "status": "done",
                    "path": str(output_path.relative_to(PROJECT_ROOT)),
                    "sha256": _sha256(output_path),
                }
            )
            manifest["shots"][shot_id] = entry
            state.write_json(MANIFEST_PATH, manifest)
            done += 1
            continue
        reference = None
        if shot_id != S001:
            reference = REFERENCE_CHARACTER
            if not reference.is_file():
                raise PipelineError("缺少角色定标参考图: " + str(reference), code=4)
        text2img = prompt_data["text2img"]
        try:
            result = media_image.generate(
                text2img["prompt"],
                text2img.get("negative_prompt", ""),
                int(prompt_data["seed"]),
                output_path,
                reference_image=reference,
                config_obj=config_obj,
            )
        except media_image.MediaError as exc:
            failed.append({"shot_id": shot_id, "error": str(exc)})
            entry.update({"status": "failed", "path": str(output_path.relative_to(PROJECT_ROOT)), "error": str(exc)})
            manifest["shots"][shot_id] = entry
            state.write_json(MANIFEST_PATH, manifest)
            if shot_id == S001:
                break
            continue
        entry.update(
            {
                "status": "done",
                "path": str(output_path.relative_to(PROJECT_ROOT)),
                "sha256": _sha256(output_path),
                "width": result["width"],
                "height": result["height"],
                "provider": result["provider"],
                "model": result["model"],
                "seed": result["seed"],
                "error": "",
            }
        )
        manifest["shots"][shot_id] = entry
        state.write_json(MANIFEST_PATH, manifest)
        done += 1
    manifest["shots"] = {key: value for key, value in manifest["shots"].items() if key in shots}
    state.write_json(MANIFEST_PATH, manifest)
    return {"requested": len(shots), "done": done, "failed": failed, "manifest": str(MANIFEST_PATH)}


def clips(
    shots_raw: str | None = None,
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    shots = _parse_shot_ids(shots_raw, PROMPTS_DIR)
    shots_by_id = _shot_map()
    manifest = _load_manifest_at(VIDEO_MANIFEST_PATH)
    done = 0
    failed: list[dict] = []
    for shot_id in shots:
        if shot_id not in shots_by_id:
            raise PipelineError(f"分镜表缺少 {shot_id}", code=4)
        prompt_data = _load_prompt(shot_id)
        first_frame = KEYFRAME_DIR / f"EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.png"
        if not first_frame.is_file():
            raise PipelineError(f"缺少关键帧 {first_frame}", code=4)
        output_path = VIDEO_DIR / f"EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.mp4"
        entry = manifest["shots"].get(shot_id, {})
        if resume and output_path.is_file() and output_path.stat().st_size > 0:
            entry.update(
                {
                    "status": "done",
                    "path": str(output_path.relative_to(PROJECT_ROOT)),
                    "sha256": _sha256(output_path),
                    "error": "",
                }
            )
            manifest["shots"][shot_id] = entry
            _write_manifest(VIDEO_MANIFEST_PATH, manifest)
            done += 1
            continue
        try:
            result = media_video.image_to_video(
                first_frame,
                prompt_data["img2video"]["prompt"],
                float(shots_by_id[shot_id]["duration_sec"]),
                output_path,
                config_obj=config_obj,
            )
        except media_video.MediaError as exc:
            failed.append({"shot_id": shot_id, "error": str(exc)})
            entry.update({"status": "failed", "path": str(output_path.relative_to(PROJECT_ROOT)), "error": str(exc)})
            manifest["shots"][shot_id] = entry
            _write_manifest(VIDEO_MANIFEST_PATH, manifest)
            continue
        entry.update(
            {
                "status": "done",
                "path": str(output_path.relative_to(PROJECT_ROOT)),
                "sha256": _sha256(output_path),
                "duration_sec": result["duration_sec"],
                "api_duration_sec": result["api_duration_sec"],
                "task_id": result["task_id"],
                "units": result.get("units"),
                "provider": result["provider"],
                "model": result["model"],
                "error": "",
            }
        )
        manifest["shots"][shot_id] = entry
        _write_manifest(VIDEO_MANIFEST_PATH, manifest)
        done += 1
    manifest["shots"] = {key: value for key, value in manifest["shots"].items() if key in shots}
    _write_manifest(VIDEO_MANIFEST_PATH, manifest)
    return {"requested": len(shots), "done": done, "failed": failed, "manifest": str(VIDEO_MANIFEST_PATH)}


def _dialogue_rows() -> list[dict]:
    with DIALOGUE_PATH.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _voice_for(character: str, selected: str, cfg: config_module.Config) -> str:
    if character == "藏经阁老者":
        env = "VOLC_TTS_VOICE_MENTOR"
    elif character == "试炼者":
        env = "VOLC_TTS_VOICE_LIE" if selected == "lie" else "VOLC_TTS_VOICE_MIRROR"
    else:
        env = "VOLC_TTS_VOICE_MENTOR"
    voice = (cfg.get(env) or "").strip()
    if not voice:
        raise PipelineError(f"缺少环境变量 {env}", code=4)
    return voice


def tts(
    dialogue_raw: str | None = None,
    all_dialogue: bool = False,
    resume: bool = False,
    config_obj: config_module.Config | None = None,
) -> dict:
    cfg = config_obj or config_module.load_config()
    protagonist = json.loads(PROTAGONIST_PATH.read_text(encoding="utf-8"))
    selected = protagonist.get("selected", "undecided")
    rows = _dialogue_rows()
    if dialogue_raw:
        wanted = {item.strip() for item in dialogue_raw.split(",") if item.strip()}
        rows = [row for row in rows if row["dialogue_id"] in wanted]
        missing = wanted - {row["dialogue_id"] for row in rows}
        if missing:
            raise PipelineError("台词表缺少: " + ", ".join(sorted(missing)), code=4)
    elif not all_dialogue and not rows:
        raise PipelineError("台词表为空", code=4)
    manifest = _load_manifest_at(TTS_MANIFEST_PATH, episode="EP01")
    manifest.setdefault("lines", {})
    done = 0
    failed: list[dict] = []
    for row in rows:
        dialogue_id = row["dialogue_id"]
        output_path = AUDIO_DIR / f"EP01_{dialogue_id}_v{config_module.MEDIA_VERSION}.mp3"
        entry = manifest["lines"].get(dialogue_id, {})
        if resume and output_path.is_file() and output_path.stat().st_size > 0:
            entry.update({"status": "done", "path": str(output_path.relative_to(PROJECT_ROOT)), "sha256": _sha256(output_path)})
            manifest["lines"][dialogue_id] = entry
            _write_manifest(TTS_MANIFEST_PATH, manifest)
            done += 1
            continue
        try:
            voice = _voice_for(row["character"], selected, cfg)
            result = media_tts.synth(row["text"], voice, output_path, config_obj=cfg)
        except (PipelineError, media_tts.MediaError) as exc:
            failed.append({"dialogue_id": dialogue_id, "error": str(exc)})
            entry.update({"status": "failed", "path": str(output_path.relative_to(PROJECT_ROOT)), "error": str(exc)})
            manifest["lines"][dialogue_id] = entry
            _write_manifest(TTS_MANIFEST_PATH, manifest)
            continue
        entry.update(
            {
                "status": "done",
                "path": str(output_path.relative_to(PROJECT_ROOT)),
                "sha256": _sha256(output_path),
                "duration_sec": result["duration_sec"],
                "mean_volume_db": result["mean_volume_db"],
                "voice": result["voice"],
                "character": row["character"],
                "text": row["text"],
                "error": "",
            }
        )
        manifest["lines"][dialogue_id] = entry
        _write_manifest(TTS_MANIFEST_PATH, manifest)
        done += 1
    return {"requested": len(rows), "done": done, "failed": failed, "manifest": str(TTS_MANIFEST_PATH)}
