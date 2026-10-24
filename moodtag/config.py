"""Non-secret user configuration for moodtag."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_ENV = "MOODTAG_CONFIG"
CONFIG_KEYS = ("source", "base_url", "model", "profile", "eagle_api", "ollama_preset")
NAMED_PROFILES_KEY = "model_profiles"
ACTIVE_PROFILE_KEY = "active_model_profile"


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
    if not raw.strip():
        return {}
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
    profiles = data.get(NAMED_PROFILES_KEY)
    active_profile = str(data.get(ACTIVE_PROFILE_KEY, "") or "").strip()
    if isinstance(profiles, dict):
        clean_profiles: dict[str, dict[str, str]] = {}
        for profile_id, raw_profile in profiles.items():
            if not isinstance(raw_profile, dict):
                continue
            clean = {
                key: str(raw_profile.get(key, "") or "").strip()
                for key in CONFIG_KEYS
                if str(raw_profile.get(key, "") or "").strip()
            }
            if clean:
                clean_profiles[str(profile_id)] = clean
        if clean_profiles:
            config[NAMED_PROFILES_KEY] = json.dumps(
                clean_profiles, ensure_ascii=False, sort_keys=True
            )
            if active_profile in clean_profiles:
                config[ACTIVE_PROFILE_KEY] = active_profile
            elif not any(config.get(key) for key in ("source", "base_url", "model")):
                active_profile = next(iter(clean_profiles))
                config[ACTIVE_PROFILE_KEY] = active_profile
            selected = clean_profiles.get(config.get(ACTIVE_PROFILE_KEY, ""), {})
            if selected:
                config.update(selected)
    return config


def save_user_config(config: dict[str, str], path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep config file self-documenting: every non-secret key exists, even unset.
    clean = {key: str(config.get(key, "") or "").strip() for key in CONFIG_KEYS}
    profiles_raw = config.get(NAMED_PROFILES_KEY)
    if profiles_raw:
        try:
            profiles = (
                json.loads(profiles_raw)
                if isinstance(profiles_raw, str)
                else profiles_raw
            )
        except json.JSONDecodeError as exc:
            raise ConfigError("Invalid named model profiles") from exc
        if not isinstance(profiles, dict):
            raise ConfigError("Named model profiles must be an object")
        clean[NAMED_PROFILES_KEY] = profiles
        clean[ACTIVE_PROFILE_KEY] = str(
            config.get(ACTIVE_PROFILE_KEY, "") or ""
        ).strip()
    rendered = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)
    return path


def update_user_config(values: dict[str, str]) -> Path:
    config = load_user_config()
    for key, value in values.items():
        if key not in CONFIG_KEYS and key not in {
            NAMED_PROFILES_KEY,
            ACTIVE_PROFILE_KEY,
        }:
            raise ConfigError(f"Unsupported config key: {key}")
        value = str(value or "").strip()
        if value:
            config[key] = value
    return save_user_config(config)


def public_config_view(
    config: dict[str, str],
    *,
    api_key_set: bool,
) -> dict[str, Any]:
    source = config.get("source") or (
        "openai-compatible" if config.get("base_url") or config.get("model") else ""
    )
    return {
        "config_path": str(config_path()),
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "source": source,
        "ollama_preset": config.get("ollama_preset", "qwen-instruct"),
        "profile": config.get("profile", "editorial") or "editorial",
        "eagle_api": config.get("eagle_api", ""),
        "api_key": "set" if api_key_set else "unset",
        "api_key_source": os.environ.get("_MOODTAG_API_KEY_SOURCE", "unset")
        if api_key_set
        else "unset",
    }
