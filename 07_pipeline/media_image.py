"""Seedream 文生图/图生图适配器。只使用标准库。"""

from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config as config_module

RETRY_DELAYS = (5, 15, 30)
RETRYABLE_STATUS = {429}


class MediaError(Exception):
    """媒体 API 失败；消息不含密钥。"""


def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 配置
        return int(response.status), response.read()


def _image_size(data: bytes) -> tuple[int, int]:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data[:2] == b"\xff\xd8":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(data):
                break
            length = struct.unpack(">H", data[index : index + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if index + 7 > len(data):
                    break
                height, width = struct.unpack(">HH", data[index + 3 : index + 7])
                return int(width), int(height)
            index += max(length, 2)
    raise MediaError("下载内容不是可识别的 PNG/JPEG")


def _data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _build_payload(
    model: str,
    prompt: str,
    negative_prompt: str,
    size: str,
    reference_image: Path | None,
) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "url",
        "watermark": False,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if reference_image is not None:
        payload["image_urls"] = [_data_uri(reference_image)]
    return payload


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


def generate(
    prompt: str,
    negative_prompt: str,
    seed: int,
    output_path: str | Path,
    reference_image: str | Path | None = None,
    size: str = "1920x1080",
    *,
    config_obj: config_module.Config | None = None,
    transport=None,
    sleep=None,
) -> dict:
    cfg = config_obj or config_module.load_config()
    api_key = (cfg.get("ARK_API_KEY") or "").strip()
    model = (cfg.get("SEEDREAM_ENDPOINT_ID") or cfg.get("SEEDREAM_MODEL_ID") or "").strip()
    if not api_key:
        raise MediaError("缺少环境变量 ARK_API_KEY")
    if not model:
        raise MediaError("缺少 SEEDREAM_ENDPOINT_ID 或 SEEDREAM_MODEL_ID")
    region = (cfg.get("ARK_REGION") or "cn-beijing").strip()
    url = f"https://ark.{region}.volces.com/api/v3/images/generations"
    ref = Path(reference_image) if reference_image else None
    if ref is not None and not ref.is_file():
        raise MediaError(f"参考图不存在: {ref}")
    payload = _build_payload(model, prompt, negative_prompt, size, ref)
    # Seedream 当前接口不保证接受 seed；仍随请求发送，便于服务端支持时复现。
    payload["seed"] = int(seed)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    transport = transport or _default_transport
    sleep = sleep or time.sleep
    last_error = "unknown"
    for attempt in range(len(RETRY_DELAYS) + 1):
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            status, raw = transport(request, 180)
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code in RETRYABLE_STATUS or 500 <= exc.code < 600:
                if attempt < len(RETRY_DELAYS):
                    sleep(RETRY_DELAYS[attempt])
                    continue
            raise MediaError(last_error) from None
        except (URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = f"网络错误: {exc.__class__.__name__}"
            if attempt < len(RETRY_DELAYS):
                sleep(RETRY_DELAYS[attempt])
                continue
            raise MediaError(last_error) from None
        if status >= 400:
            raise MediaError(f"HTTP {status}")
        try:
            data = json.loads(raw.decode("utf-8"))
            image_url = data["data"][0]["url"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise MediaError("Seedream 响应缺少 data[0].url") from None
        break

    try:
        image_status, image_bytes = _default_transport(Request(image_url, method="GET"), 180)
    except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise MediaError(f"下载关键帧失败: {exc.__class__.__name__}") from None
    if image_status >= 400 or not image_bytes:
        raise MediaError(f"下载关键帧失败: HTTP {image_status}")
    width, height = _image_size(image_bytes)
    expected_width, expected_height = (int(part) for part in size.lower().split("x", 1))
    if (width, height) != (expected_width, expected_height):
        raise MediaError(f"图片尺寸 {width}x{height} 与请求 {size} 不一致")
    target = Path(output_path)
    _write_atomic(target, image_bytes)
    return {
        "provider": "seedream",
        "model": model,
        "path": str(target),
        "bytes": len(image_bytes),
        "width": width,
        "height": height,
        "seed": int(seed),
    }
