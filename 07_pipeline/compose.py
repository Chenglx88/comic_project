"""成片合成：统一规格、拼接、混音、软字幕与最终校验。"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import config as config_module
import state
from errors import PipelineError

PROJECT_ROOT = config_module.PROJECT_ROOT
SHOTS_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "shots.csv"
DIALOGUE_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "dialogue.csv"
OVERLAYS_PATH = PROJECT_ROOT / "03_storyboard" / "EP01" / "overlays.csv"
VIDEO_MANIFEST = PROJECT_ROOT / "06_render" / "EP01" / "videos_manifest.json"
TTS_MANIFEST = PROJECT_ROOT / "05_assets" / "audio" / "EP01_tts_manifest.json"
VIDEO_DIR = PROJECT_ROOT / "06_render" / "videos"
EPISODE_DIR = PROJECT_ROOT / "06_render" / "episodes"
AUDIO_DIR = PROJECT_ROOT / "05_assets" / "audio"
WORK_DIR = PROJECT_ROOT / ".state" / "work" / "EP01"


class ComposeError(Exception):
    """ffmpeg 或素材校验失败。"""


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise ComposeError("命令失败: " + " ".join(cmd[:4]) + "；" + " | ".join(tail))


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            config_module.tool_path("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ComposeError(f"ffprobe 失败: {path}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ComposeError(f"ffprobe 输出不是 JSON: {path}") from None


def _load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _ass_time(seconds: float) -> str:
    centis = int(round(seconds * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r", "")
        .replace("\n", "\\N")
    )


def _build_overlays_ass(work: Path) -> Path | None:
    if not OVERLAYS_PATH.is_file():
        return None
    rows = [row for row in _load_rows(OVERLAYS_PATH) if (row.get("title") or "").strip()]
    if not rows:
        return None
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: Info,WenQuanYi Zen Hei,34,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H80000000,0,0,0,0,100,100,0,0,3,2,0,8,60,60,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [header]
    for row in rows:
        start = _ass_time(float(row["start_sec"]))
        end = _ass_time(float(row["end_sec"]))
        title = _ass_escape((row.get("title") or "").strip())
        body = _ass_escape((row.get("body") or "").strip())
        text = f"{{\\fad(200,200)\\b1}}{title}{{\\b0}}"
        if body:
            text += f"\\N{body}"
        lines.append(f"Dialogue: 0,{start},{end},Info,,0,0,0,,{text}\n")
    path = work / "overlays.ass"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _burn_overlays(video: Path, work: Path) -> Path:
    ass_path = _build_overlays_ass(work)
    if ass_path is None:
        return video
    target = work / "video_overlays.mp4"
    _run(
        [
            config_module.tool_path("ffmpeg"),
            "-y",
            "-i",
            str(video),
            "-vf",
            f"ass={ass_path.as_posix()}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-an",
            str(target),
        ]
    )
    return target


def _timeline(shots: list[dict]) -> tuple[dict[str, float], float]:
    starts: dict[str, float] = {}
    cursor = 0.0
    for shot in shots:
        starts[shot["shot_id"]] = cursor
        cursor += float(shot["duration_sec"])
    return starts, cursor


def _normalize_videos(shots: list[dict], work: Path) -> Path:
    normalized = work / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    list_lines: list[str] = []
    for shot in shots:
        shot_id = shot["shot_id"]
        source = VIDEO_DIR / f"EP01_computer_{shot_id}_v{config_module.MEDIA_VERSION}.mp4"
        if not source.is_file():
            raise ComposeError(f"缺少视频片段: {source}")
        target = normalized / f"{shot_id}.mp4"
        duration = float(shot["duration_sec"])
        _run(
            [
                config_module.tool_path("ffmpeg"),
                "-y",
                "-i",
                str(source),
                "-t",
                f"{duration:.3f}",
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,"
                f"tpad=stop_mode=clone:stop_duration=2",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "18",
                str(target),
            ]
        )
        list_lines.append(f"file '{target.as_posix()}'")
    concat_list = work / "concat.txt"
    concat_list.write_text("\n".join(list_lines) + "\n", encoding="utf-8")
    concat_video = work / "video_concat.mp4"
    _run(
        [
            config_module.tool_path("ffmpeg"),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(concat_video),
        ]
    )
    return concat_video


def _build_voice(
    shots: list[dict],
    dialogue: list[dict],
    tts_manifest: dict,
    total: float,
    work: Path,
) -> Path:
    starts, _ = _timeline(shots)
    silence = work / "silence.wav"
    _run(
        [
            config_module.tool_path("ffmpeg"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            f"{total:.3f}",
            "-c:a",
            "pcm_s16le",
            str(silence),
        ]
    )
    shot_for_dialogue: dict[str, str] = {}
    for shot in shots:
        dialogue_id = (shot.get("dialogue_id") or "").strip()
        if dialogue_id:
            shot_for_dialogue.setdefault(dialogue_id, shot["shot_id"])
    inputs: list[dict] = []
    for row in dialogue:
        dialogue_id = row["dialogue_id"]
        entry = tts_manifest.get("lines", {}).get(dialogue_id, {})
        if entry.get("status") != "done":
            raise ComposeError(f"台词 {dialogue_id} 尚未完成 TTS")
        path = PROJECT_ROOT / entry["path"]
        if not path.is_file():
            raise ComposeError(f"缺少配音文件: {path}")
        shot_id = shot_for_dialogue.get(dialogue_id)
        if shot_id is None:
            raise ComposeError(f"台词 {dialogue_id} 没有对应镜头")
        inputs.append({"path": path, "start": starts[shot_id]})
    if not inputs:
        return silence
    voice = work / "voice.wav"
    cmd = [config_module.tool_path("ffmpeg"), "-y", "-i", str(silence)]
    for item in inputs:
        cmd += ["-i", str(item["path"])]
    filters: list[str] = []
    labels: list[str] = ["[0:a]"]
    for index, item in enumerate(inputs, start=1):
        delay = int(round(item["start"] * 1000))
        filters.append(
            f"[{index}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay}|{delay}[a{index}]"
        )
        labels.append(f"[a{index}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0,volume=1.78[out]"
    )
    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(voice),
    ]
    _run(cmd)
    return voice


def _bgm_sources() -> list[Path]:
    """bgm 目录下的非隐藏文件，按名称排序。"""
    bgm_dir = AUDIO_DIR / "bgm"
    if not bgm_dir.is_dir():
        return []
    return sorted(
        path for path in bgm_dir.iterdir() if path.is_file() and not path.name.startswith(".")
    )


def _build_bgm(total: float, work: Path) -> Path | None:
    """把已定稿 BGM 循环铺满成片时长，降低音量并在头尾淡入淡出。"""
    sources = _bgm_sources()
    if not sources:
        return None
    target = work / "bgm.wav"
    fade_out = max(total - 3.0, 0.0)
    _run(
        [
            config_module.tool_path("ffmpeg"),
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(sources[0]),
            "-t",
            f"{total:.3f}",
            "-af",
            f"volume=0.07,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.3f}:d=3",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )
    return target


def _mux(
    video: Path,
    voice: Path,
    srt: Path,
    bgm: Path | None,
    total: float,
    output: Path,
) -> None:
    """封装视频/人声/字幕，有 BGM 时与其混音后再封装。"""
    cmd = [
        config_module.tool_path("ffmpeg"),
        "-y",
        "-i",
        str(video),
        "-i",
        str(voice),
        "-i",
        str(srt),
    ]
    if bgm is not None:
        cmd += ["-i", str(bgm)]
    cmd += ["-map", "0:v:0"]
    if bgm is not None:
        cmd += [
            "-filter_complex",
            "[1:a][3:a]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map",
            "[aout]",
        ]
    else:
        cmd += ["-map", "1:a:0"]
    cmd += [
        "-map",
        "2:s:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=chi",
        "-movflags",
        "+faststart",
        "-t",
        f"{total:.3f}",
        str(output),
    ]
    _run(cmd)


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3600 * 1000)
    minutes, millis = divmod(millis, 60 * 1000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _build_srt(shots: list[dict], dialogue: list[dict], tts_manifest: dict) -> Path:
    starts, _ = _timeline(shots)
    shot_for_dialogue: dict[str, str] = {}
    for shot in shots:
        dialogue_id = (shot.get("dialogue_id") or "").strip()
        if dialogue_id:
            shot_for_dialogue.setdefault(dialogue_id, shot["shot_id"])
    lines: list[str] = []
    for index, row in enumerate(dialogue, start=1):
        dialogue_id = row["dialogue_id"]
        shot_id = shot_for_dialogue.get(dialogue_id)
        if shot_id is None:
            continue
        duration = float(row.get("duration_sec") or 0)
        entry = tts_manifest.get("lines", {}).get(dialogue_id, {})
        duration = min(duration or float(entry.get("duration_sec") or 0), float(next(
            shot["duration_sec"] for shot in shots if shot["shot_id"] == shot_id
        )))
        start = starts[shot_id]
        lines.append(str(index))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(start + max(duration, 0.5))}")
        lines.append(row["text"])
        lines.append("")
    path = (
        PROJECT_ROOT
        / "06_render"
        / "EP01"
        / f"EP01_subtitles_v{config_module.MEDIA_VERSION}.srt"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def validate_final(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file() or path.stat().st_size == 0:
        return [f"成片不存在或为空: {path}"]
    data = _probe(path)
    duration = float(data.get("format", {}).get("duration", 0))
    if not 200 <= duration <= 220:
        errors.append(f"成片时长 {duration:.2f}s 越界（200-220s）")
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video) != 1:
        errors.append(f"视频流数量应为 1，实际 {len(video)}")
    if len(audio) != 1:
        errors.append(f"音频流数量应为 1，实际 {len(audio)}")
    if video:
        stream = video[0]
        if (stream.get("width"), stream.get("height")) != (1920, 1080):
            errors.append(f"分辨率应为 1920x1080，实际 {stream.get('width')}x{stream.get('height')}")
        if stream.get("codec_name") != "h264":
            errors.append(f"视频编码应为 h264，实际 {stream.get('codec_name')}")
        if stream.get("r_frame_rate") not in {"30/1", "30"}:
            errors.append(f"帧率应为 30fps，实际 {stream.get('r_frame_rate')}")
    if audio:
        stream = audio[0]
        if stream.get("codec_name") != "aac":
            errors.append(f"音频编码应为 aac，实际 {stream.get('codec_name')}")
        if int(stream.get("sample_rate") or 0) != 48000:
            errors.append(f"采样率应为 48000，实际 {stream.get('sample_rate')}")
        if int(stream.get("channels") or 0) != 2:
            errors.append(f"声道数应为 2，实际 {stream.get('channels')}")
    return errors


def compose(version: int = 1, allow_silent_bgm: bool = False) -> dict:
    shots = _load_rows(SHOTS_PATH)
    dialogue = _load_rows(DIALOGUE_PATH)
    videos_manifest = json.loads(VIDEO_MANIFEST.read_text(encoding="utf-8"))
    tts_manifest = json.loads(TTS_MANIFEST.read_text(encoding="utf-8"))
    missing_videos = [shot["shot_id"] for shot in shots if videos_manifest.get("shots", {}).get(shot["shot_id"], {}).get("status") != "done"]
    if missing_videos:
        raise ComposeError("视频未完成: " + ", ".join(missing_videos))
    if not allow_silent_bgm and not _bgm_sources():
        state.append_blocker(
            "compose 缺少已授权 BGM/SFX 素材；需用户书面确认无 BGM 或提供素材后重跑"
        )
        raise PipelineError("缺少已授权 BGM/SFX；确认静音后加 --allow-silent-bgm", code=7)
    work = WORK_DIR / f"compose_v{version}"
    work.mkdir(parents=True, exist_ok=True)
    _, total = _timeline(shots)
    bgm = None if allow_silent_bgm else _build_bgm(total, work)
    concat_video = _normalize_videos(shots, work)
    concat_video = _burn_overlays(concat_video, work)
    voice = _build_voice(shots, dialogue, tts_manifest, total, work)
    srt = _build_srt(shots, dialogue, tts_manifest)
    EPISODE_DIR.mkdir(parents=True, exist_ok=True)
    output = EPISODE_DIR / f"EP01_final_v{version}.mp4"
    _mux(concat_video, voice, srt, bgm, total, output)
    errors = validate_final(output)
    if errors:
        raise ComposeError("成片校验失败：" + "; ".join(errors))
    return {
        "path": str(output),
        "duration_sec": total,
        "shots": len(shots),
        "dialogue": len(dialogue),
        "srt": str(srt),
        "sha256": __import__("hashlib").sha256(output.read_bytes()).hexdigest(),
    }
