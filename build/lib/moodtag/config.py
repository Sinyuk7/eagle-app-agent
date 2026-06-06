"""Non-secret user configuration for moodtag."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_ENV = "MOODTAG_CONFIG"
CONFIG_KEYS = ("base_url", "fallback_base_url", "model", "eagle_api")


class ConfigError(RuntimeError):
    """Expected config-layer error."""


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    xdg_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return root / "moodtag" / "config.json"


def load_user_config(path: Path | None = None) -> dict[str, str]:
    path = path or config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid config JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a JSON object: {path}")
    config: dict[str, str] = {}
    for key in CONFIG_KEYS:
        value = data.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            config[key] = value
    return config


def save_user_config(config: dict[str, str], path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: str(config[key]).strip() for key in CONFIG_KEYS if config.get(key)}
    path.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def update_user_config(values: dict[str, str]) -> Path:
    config = load_user_config()
    for key, value in values.items():
        if key not in CONFIG_KEYS:
            raise ConfigError(f"Unsupported config key: {key}")
        value = str(value or "").strip()
        if value:
            config[key] = value
    return save_user_config(config)


def public_config_view(config: dict[str, str], *, api_key_set: bool) -> dict[str, Any]:
    return {
        "config_path": str(config_path()),
        "base_url": config.get("base_url", ""),
        "fallback_base_url": config.get("fallback_base_url", ""),
        "model": config.get("model", ""),
        "eagle_api": config.get("eagle_api", ""),
        "api_key": "set" if api_key_set else "unset",
    }
