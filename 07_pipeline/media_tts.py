"""火山 TTS 适配器：单条台词合成、音频校验。"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config as config_module

ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


class MediaError(Exception):
    """TTS 失败；消息不含密钥。"""


def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 配置
        return int(response.status), response.read()


SUCCESS_CODES = (0, "0", None, 20000000, "20000000")


def _parse_audio(raw: bytes) -> bytes:
    """解析 NDJSON/SSE/连续 JSON：取 data 字段的 base64 音频块。

    火山 unidirectional 接口用 code=20000000 表示合成结束，不是错误；
    响应可能是带换行的 SSE，也可能是首尾相接的 JSON 对象，因此按对象
    起点逐个 raw_decode，而不是按行解析。
    """
    text = raw.decode("utf-8", errors="replace")
    decoder = json.JSONDecoder()
    chunks: list[bytes] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            item, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = end
        if not isinstance(item, dict):
            continue
        code = item.get("code", item.get("status_code", 0))
        if code not in SUCCESS_CODES:
            raise MediaError(f"TTS 返回错误码 {code}")
        data = item.get("data")
        if isinstance(data, str) and data:
            try:
                chunks.append(base64.b64decode(data))
            except ValueError as exc:
                raise MediaError("TTS 音频块不是合法 base64") from exc
    if not chunks:
        raise MediaError("TTS 响应没有音频数据")
    return b"".join(chunks)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            config_module.tool_path("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = float(proc.stdout.strip())
    except ValueError:
        raise MediaError("ffprobe 无法读取 TTS 时长") from None
    if duration <= 0:
        raise MediaError("TTS 音频时长为 0")
    vol = subprocess.run(
        [config_module.tool_path("ffmpeg"), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol.stderr)
    mean_volume = float(match.group(1)) if match else None
    if mean_volume is not None and mean_volume <= -50:
        raise MediaError(f"TTS 音频接近静音（mean_volume {mean_volume} dB）")
    return {"duration_sec": duration, "mean_volume_db": mean_volume}


def synth(
    text: str,
    voice: str,
    output_path: str | Path,
    speed: int = 0,
    *,
    config_obj: config_module.Config | None = None,
    transport=None,
) -> dict:
    cfg = config_obj or config_module.load_config()
    api_key = (cfg.get("VOLC_TTS_API_KEY") or "").strip()
    cluster = (cfg.get("VOLC_TTS_CLUSTER") or "").strip()
    if not api_key:
        raise MediaError("缺少环境变量 VOLC_TTS_API_KEY")
    if not cluster:
        raise MediaError("缺少环境变量 VOLC_TTS_CLUSTER")
    if not voice:
        raise MediaError("缺少音色 ID")
    payload = {
        "user": {"uid": "wujing-ep01"},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": int(speed)},
        },
    }
    request = Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": cluster,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    transport = transport or _default_transport
    try:
        status, raw = transport(request, 180)
    except HTTPError as exc:
        raise MediaError(f"TTS HTTP {exc.code}") from None
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise MediaError(f"TTS 网络错误: {exc.__class__.__name__}") from None
    if status >= 400:
        raise MediaError(f"TTS HTTP {status}")
    audio = _parse_audio(raw)
    target = Path(output_path)
    _write_atomic(target, audio)
    probe = _probe(target)
    return {
        "provider": "volc_tts",
        "voice": voice,
        "path": str(target),
        "bytes": len(audio),
        **probe,
    }
