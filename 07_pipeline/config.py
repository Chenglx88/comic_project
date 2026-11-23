"""安全加载环境变量与路由配置。只判断键是否存在，不打印值。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
BIN_DIR = PIPELINE_DIR / "bin"
MEDIA_VERSION = 2
DEFAULT_ENV_CANDIDATES = (
    PIPELINE_DIR / "config" / ".env",
    PROJECT_ROOT / ".env",
)
ROUTING_PATH = PIPELINE_DIR / "config" / "routing.json"


def tool_path(name: str) -> str:
    """优先用项目内静态二进制，回退到 PATH。"""
    candidate = BIN_DIR / name
    return str(candidate) if candidate.is_file() else name


class ConfigError(Exception):
    """配置缺失或格式错误。消息中只出现键名，不包含值。"""


def parse_env_text(text: str) -> dict[str, str]:
    """解析 KEY=VALUE / export KEY=VALUE、注释与成对引号；不执行 shell。"""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


@dataclass
class Config:
    values: dict[str, str] = field(default_factory=dict)
    sources: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def from_files(cls, paths: list[Path]) -> "Config":
        """按顺序加载，后面的文件覆盖前面的同名键。"""
        config = cls()
        encodings = ("utf-8",)
        for path in paths:
            path = Path(path)
            if not path.is_file():
                continue
            text = path.read_text(encoding=encodings[0])
            for key, value in parse_env_text(text).items():
                config.values[key] = value
                config.sources[key] = path
        return config

    def get(self, name: str, default: str | None = None) -> str | None:
        value = self.values.get(name)
        return default if value is None else value

    def present(self, name: str) -> bool:
        return bool((self.values.get(name) or "").strip())

    def require(self, names: list[str]) -> dict[str, str]:
        missing = [name for name in names if not self.present(name)]
        if missing:
            raise ConfigError("缺少环境变量: " + ", ".join(missing))
        return {name: self.values[name] for name in names}

    def redacted_snapshot(self, names: list[str]) -> dict[str, str]:
        return {name: ("<set>" if self.present(name) else "<missing>") for name in names}


def load_config(paths: list[Path] | None = None) -> Config:
    """默认先找 07_pipeline/config/.env，不存在再回退项目根 .env。"""
    if paths is None:
        first = next((path for path in DEFAULT_ENV_CANDIDATES if path.is_file()), None)
        paths = [first] if first is not None else []
    return Config.from_files(paths)


def load_routing(path: Path | None = None) -> dict:
    routing_path = Path(path) if path is not None else ROUTING_PATH
    try:
        routing = json.loads(routing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"路由配置不可读: {routing_path} ({exc.__class__.__name__})") from exc
    if routing.get("fallback") != "none":
        raise ConfigError("routing.json 的 fallback 必须为 none")
    layers = routing.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise ConfigError("routing.json 缺少 layers")
    return routing
