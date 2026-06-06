"""Prompt template loading and rendering."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from .contract import JSON_TEMPLATE, CoreError
from .taxonomy import render_taxonomy_for_prompt, render_use_intents_for_prompt

PROMPT_PACKAGE = "moodtag_core.resources.prompts"
SYSTEM_PROMPT_NAME = "moodtag-system-prompt.txt"
USER_PROMPT_NAME = "moodtag-user-prompt.txt"
SYSTEM_PROMPT_PATH = Path(SYSTEM_PROMPT_NAME)
USER_PROMPT_PATH = Path(USER_PROMPT_NAME)


def read_template(path: Path | None = None, *, resource_name: str | None = None) -> str:
    try:
        if resource_name:
            text = (
                resources.files(PROMPT_PACKAGE)
                .joinpath(resource_name)
                .read_text(encoding="utf-8")
                .strip()
            )
            label = resource_name
        elif path is not None:
            text = path.read_text(encoding="utf-8").strip()
            label = str(path)
        else:
            raise CoreError("Missing prompt template path")
    except FileNotFoundError as exc:
        raise CoreError(f"Prompt template not found: {resource_name or path}") from exc
    if not text:
        raise CoreError(f"Prompt template is empty: {label}")
    return text


def read_system_prompt(path: Path | None = None) -> str:
    if path is not None:
        return read_template(path)
    return read_template(resource_name=SYSTEM_PROMPT_NAME)


def render_user_prompt(taxonomy: dict[str, list[str]], path: Path | None = None) -> str:
    template = (
        read_template(path)
        if path is not None
        else read_template(resource_name=USER_PROMPT_NAME)
    )
    return (
        template.replace("{{json_template}}", JSON_TEMPLATE)
        .replace("{{taxonomy}}", render_taxonomy_for_prompt(taxonomy))
        .replace("{{use_intents}}", render_use_intents_for_prompt())
    )
