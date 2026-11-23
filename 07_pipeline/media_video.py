"""可灵图生视频适配器：提交任务、轮询、下载与 ffprobe 校验。"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config as config_module

CREATE_URL = "https://api-beijing.klingai.com/image-to-video/kling-3.0"
TASK_URL = "https://api-beijing.klingai.com/tasks"
RETRY_DELAYS = (5, 15, 30)
RETRYABLE_STATUS = {429}


class MediaError(Exception):
    """视频 API 失败；消息不含密钥。"""


def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 配置
        return int(response.status), response.read()


def _request_json(headers: dict, url: str, payload: dict | None, transport, timeout: int = 180) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST" if payload is not None else "GET")
    try:
        status, raw = transport(request, timeout)
    except HTTPError as exc:
        raise MediaError(f"可灵 HTTP {exc.code}") from None
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise MediaError(f"可灵网络错误: {exc.__class__.__name__}") from None
    if status >= 400:
        raise MediaError(f"可灵 HTTP {status}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MediaError("可灵响应不是合法 JSON") from None


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


def _probe(path: Path, expected_duration: float) -> dict:
    proc = subprocess.run(
        [
            config_module.tool_path("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        data = json.loads(proc.stdout)
        duration = float(data["format"]["duration"])
        streams = data.get("streams", [])
    except (ValueError, KeyError, TypeError):
        raise MediaError("ffprobe 无法读取视频信息") from None
    if duration <= 0:
        raise MediaError("视频时长为 0")
    if abs(duration - expected_duration) > 0.5:
        raise MediaError(f"视频时长 {duration:.2f}s 与预期 {expected_duration:.2f}s 相差超过 0.5s")
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise MediaError("视频缺少视频流")
    return {"duration_sec": duration, "streams": streams}


def _extract_task(data: dict) -> dict:
    task = data.get("data", data)
    if isinstance(task, list):
        task = task[0] if task else {}
    if not isinstance(task, dict):
        raise MediaError("可灵响应缺少任务对象")
    return task


def _extract_video_url(task: dict) -> str:
    """兼容新旧两套返回结构。

    新版 /tasks 查询把结果直链放在任务对象顶层 url/outputs；
    经典 v1 接口放在 task_result.videos[0].url。
    """
    candidates: list[object] = [task.get("url"), task.get("video_url")]
    containers: list[object] = [task.get("outputs")]
    for key in ("task_result", "result"):
        value = task.get(key)
        if isinstance(value, dict):
            candidates.append(value.get("url"))
            containers.append(value.get("videos"))
    for container in containers:
        if not isinstance(container, list):
            continue
        for item in container:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                candidates.append(item.get("url") or item.get("video_url"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def image_to_video(
    first_frame_path: str | Path,
    prompt: str,
    duration_sec: float,
    output_path: str | Path,
    resolution: str = "1080p",
    *,
    config_obj: config_module.Config | None = None,
    transport=None,
    sleep=None,
    poll_interval: int = 10,
    timeout_sec: int = 1800,
) -> dict:
    cfg = config_obj or config_module.load_config()
    api_key = (cfg.get("KLING_API_KEY") or "").strip()
    model = (cfg.get("KLING_MODEL") or "kling-3.0").strip()
    if not api_key:
        raise MediaError("缺少环境变量 KLING_API_KEY")
    first_frame = Path(first_frame_path)
    if not first_frame.is_file():
        raise MediaError(f"首帧不存在: {first_frame}")
    api_duration = 5 if float(duration_sec) <= 5 else 10
    payload = {
        "model": model,
        "contents": [
            {"type": "prompt", "text": prompt},
            {
                "type": "first_frame",
                "url": base64.b64encode(first_frame.read_bytes()).decode("ascii"),
            },
        ],
        "settings": {
            "resolution": resolution,
            "duration": api_duration,
            "audio": "off",
            "multi_shot": False,
        },
        "options": {"watermark_info": {"enabled": False}},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    transport = transport or _default_transport
    sleep = sleep or time.sleep
    created = _request_json(headers, CREATE_URL, payload, transport)
    task = _extract_task(created)
    task_id = task.get("id") or task.get("task_id")
    if not task_id:
        raise MediaError("可灵响应缺少 task id")
    deadline = time.monotonic() + timeout_sec
    while True:
        current = _extract_task(_request_json(headers, f"{TASK_URL}?task_ids={task_id}", None, transport))
        status = str(current.get("task_status") or current.get("status") or "").lower()
        if status in {"succeed", "succeeded", "success"}:
            break
        if status in {"failed", "error"}:
            raise MediaError(f"可灵任务失败: {current.get('task_status_msg') or status}")
        if time.monotonic() >= deadline:
            raise MediaError(f"可灵任务轮询超时: {task_id}")
        sleep(poll_interval)
    video_url = _extract_video_url(current)
    if not video_url:
        fields = ",".join(sorted(current)) or "<none>"
        raise MediaError(f"可灵任务成功但没有视频 URL（字段: {fields}）")
    try:
        status, raw = transport(Request(video_url, method="GET"), 300)
    except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise MediaError(f"下载视频失败: {exc.__class__.__name__}") from None
    if status >= 400 or not raw:
        raise MediaError(f"下载视频失败: HTTP {status}")
    target = Path(output_path)
    _write_atomic(target, raw)
    # 可灵只出 5s/10s 档；按实际下单档位校验，成片阶段再裁到分镜时长。
    probe = _probe(target, float(api_duration))
    usage = current.get("usage") if isinstance(current.get("usage"), dict) else {}
    return {
        "provider": "kling",
        "model": model,
        "task_id": task_id,
        "path": str(target),
        "bytes": len(raw),
        "api_duration_sec": api_duration,
        "units": current.get("final_unit_deduction") or current.get("units") or usage.get("units"),
        **probe,
    }
