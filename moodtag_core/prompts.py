"""Prompt template loading and rendering."""

from __future__ import annotations

from pathlib import Path

from .contract import CoreError, JSON_TEMPLATE
from .taxonomy import render_taxonomy_for_prompt, render_use_intents_for_prompt


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = ROOT / "prompts"
SYSTEM_PROMPT_PATH = PROMPT_DIR / "moodtag-system-prompt.txt"
USER_PROMPT_PATH = PROMPT_DIR / "moodtag-user-prompt.txt"


def read_template(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise CoreError(f"Prompt template not found: {path}") from exc
    if not text:
        raise CoreError(f"Prompt template is empty: {path}")
    return text


def read_system_prompt(path: Path = SYSTEM_PROMPT_PATH) -> str:
    return read_template(path)


def render_user_prompt(
    taxonomy: dict[str, list[str]], path: Path = USER_PROMPT_PATH
) -> str:
    template = read_template(path)
    return (
        template.replace("{{json_template}}", JSON_TEMPLATE)
        .replace("{{taxonomy}}", render_taxonomy_for_prompt(taxonomy))
        .replace("{{use_intents}}", render_use_intents_for_prompt())
    )

