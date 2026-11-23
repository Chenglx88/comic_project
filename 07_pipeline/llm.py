"""统一 OpenAI 兼容 Chat Completions 客户端，模型 ID 必须来自配置。"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config as config_module
import state

RETRY_DELAYS = (2, 4, 8)
RETRYABLE_STATUS = {429}


class LLMError(Exception):
    """API 调用失败；消息与属性均已脱敏，不含请求头或 key。"""

    def __init__(self, summary: str, status: int | None = None):
        super().__init__(summary)
        self.status = status
        self.summary = summary


def resolve_layer(layer: str, cfg: config_module.Config | None = None) -> dict:
    """把 routing 层配置与 env 合并；缺失值用 <missing> 占位。"""
    cfg = cfg or config_module.load_config()
    routing = config_module.load_routing()
    entry = routing["layers"].get(layer)
    if not isinstance(entry, dict):
        raise LLMError(f"routing.json 缺少层 {layer}")
    base_env = entry.get("base_url_env")
    base_url = (cfg.get(base_env) if base_env and cfg.present(base_env) else None) or entry.get(
        "base_url"
    )
    api_key = cfg.get(entry["api_key_env"])
    model = entry.get("model") or cfg.get(entry["model_env"])
    return {
        "provider": entry.get("provider"),
        "base_url": (base_url or "").rstrip("/"),
        "api_key": api_key if (api_key or "").strip() else "<missing>",
        "model": model if (model or "").strip() else "<missing>",
        "api_key_env": entry["api_key_env"],
        "model_env": entry["model_env"],
        "max_tokens": int(entry.get("max_tokens", 8192)),
        "search": bool(entry.get("search", False)),
    }


def _default_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 配置
        return int(response.status), response.read()


def _error_summary(status: int | None, reason: str) -> str:
    prefix = f"HTTP {status}: " if status is not None else ""
    return (prefix + reason)[:300]


def chat(
    layer: str,
    messages: list[dict],
    max_tokens: int | None = None,
    response_format: str | None = None,
    timeout: int = 180,
    *,
    transport=None,
    config: config_module.Config | None = None,
    sleep=None,
    run_log: bool = True,
    episode: str = "EP01",
) -> dict:
    """调用一层模型。transport/sleep 仅供离线测试注入。"""
    cfg = config or config_module.load_config()
    resolved = resolve_layer(layer, cfg)
    if resolved["api_key"] == "<missing>":
        raise LLMError(f"缺少环境变量 {resolved['api_key_env']}（{layer}）")
    if resolved["model"] == "<missing>":
        raise LLMError(f"缺少环境变量 {resolved['model_env']}（{layer}）")

    payload: dict = {
        "model": resolved["model"],
        "messages": messages,
        "max_tokens": int(max_tokens or resolved["max_tokens"]),
    }
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if resolved["search"] and layer == "L1":
        payload["web_search_options"] = {"enable": True, "search_source": "standard"}

    url = f"{resolved['base_url']}/chat/completions"
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    transport = transport or _default_transport
    sleep = sleep or time.sleep

    last_error = "unknown"
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            status, body = transport(request, timeout)
        except HTTPError as exc:
            last_error = _error_summary(exc.code, "HTTP error")
            if exc.code in RETRYABLE_STATUS or 500 <= exc.code < 600:
                if attempt < len(RETRY_DELAYS):
                    sleep(RETRY_DELAYS[attempt])
                    continue
                raise LLMError(last_error, status=exc.code) from None
            raise LLMError(last_error, status=exc.code) from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            last_error = _error_summary(None, "网络错误或超时")
            if attempt < len(RETRY_DELAYS):
                sleep(RETRY_DELAYS[attempt])
                continue
            raise LLMError(last_error) from None

        status = int(status)
        if status in RETRYABLE_STATUS or 500 <= status < 600:
            last_error = _error_summary(status, "服务端可重试错误")
            if attempt < len(RETRY_DELAYS):
                sleep(RETRY_DELAYS[attempt])
                continue
            raise LLMError(last_error, status=status)
        if status >= 400:
            raise LLMError(_error_summary(status, "请求被拒绝"), status=status)

        try:
            payload_out = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LLMError(_error_summary(status, "响应不是合法 JSON"), status=status) from None

        try:
            choice = payload_out["choices"][0]
            content = choice["message"].get("content")
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LLMError(_error_summary(status, "响应缺少 choices/message"), status=status) from None

        if not content or finish_reason == "length":
            if run_log:
                try:
                    state.log_response(
                        layer,
                        {
                            "model": payload_out.get("model", resolved["model"]),
                            "http_status": status,
                            "usage": payload_out.get("usage"),
                            "finish_reason": finish_reason,
                            "content": content or "",
                        },
                        episode=episode,
                    )
                except OSError:
                    pass
            raise LLMError(
                "truncated: 内容为空或触达长度上限，请提高 max_tokens",
                status=status,
            )

        result = {
            "content": content,
            "usage": payload_out.get("usage"),
            "finish_reason": finish_reason,
            "model": payload_out.get("model", resolved["model"]),
            "http_status": status,
        }
        if run_log:
            try:
                state.log_response(layer, result, episode=episode)
            except OSError:
                pass
        return result

    raise LLMError(last_error or "unknown")
