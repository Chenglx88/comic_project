"""豆包多模态视觉抽检：只报告，不改产物。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config as config_module

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"


class MediaError(Exception):
    """视觉审计失败；消息不含密钥。"""


def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 配置
        return int(response.status), response.read()


def _image_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def audit_images(
    paths: list[str | Path],
    prompt: str,
    *,
    config_obj: config_module.Config | None = None,
    transport=None,
    max_tokens: int = 4096,
) -> dict:
    cfg = config_obj or config_module.load_config()
    api_key = (cfg.get("ARK_API_KEY") or "").strip()
    model = (cfg.get("DOUBAO_ENDPOINT_ID") or "").strip()
    if not api_key:
        raise MediaError("缺少环境变量 ARK_API_KEY")
    if not model:
        raise MediaError("缺少环境变量 DOUBAO_ENDPOINT_ID")
    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in paths:
        image_path = Path(path)
        if not image_path.is_file():
            raise MediaError(f"抽检图不存在: {image_path}")
        content.append({"type": "image_url", "image_url": {"url": _image_uri(image_path)}})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    request = Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    transport = transport or _default_transport
    try:
        status, raw = transport(request, 180)
    except HTTPError as exc:
        raise MediaError(f"豆包视觉 HTTP {exc.code}") from None
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise MediaError(f"豆包视觉网络错误: {exc.__class__.__name__}") from None
    if status >= 400:
        raise MediaError(f"豆包视觉 HTTP {status}")
    try:
        data = json.loads(raw.decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        raise MediaError("豆包视觉响应格式不正确") from None
    return {"model": model, "text": text, "usage": data.get("usage")}
