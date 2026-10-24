"""Small locale resolver for human-facing terminal strings."""

from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache


def language() -> str:
    override = os.environ.get("MOODTAG_LANG", "").strip().lower()
    if override:
        return "zh" if override.startswith("zh") else "en"
    return _system_language()


@lru_cache(maxsize=1)
def _system_language() -> str:
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_language = next(
                iter(re.findall(r"['\"]([^'\"]+)['\"]", result.stdout)), ""
            )
            return "zh" if first_language.lower().startswith("zh") else "en"
    except (OSError, subprocess.TimeoutExpired):
        pass

    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key, "").lower()
        if value:
            return "zh" if value.startswith("zh") else "en"
    return "en"


def tr(english: str, chinese: str) -> str:
    return chinese if language() == "zh" else english
