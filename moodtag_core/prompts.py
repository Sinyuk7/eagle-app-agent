"""Prompt template loading and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

from .contract import DEFAULT_JSON_TEMPLATE, EDITORIAL_JSON_TEMPLATE, CoreError
from .taxonomy import render_taxonomy_for_prompt, render_use_intents_for_prompt

PROMPT_PACKAGE = "moodtag_core.resources.prompts"
SYSTEM_PROMPT_NAME = "moodtag-system-prompt.txt"
USER_PROMPT_NAME = "moodtag-user-prompt.txt"
SYSTEM_PROMPT_PATH = Path(SYSTEM_PROMPT_NAME)
USER_PROMPT_PATH = Path(USER_PROMPT_NAME)


@dataclass(frozen=True)
class PromptProfile:
    """Prompt resources used for one analysis profile."""

    id: str
    system_prompt: str
    user_prompt: str
    json_template: str
    taxonomy_resource: str


PROMPT_PROFILES: dict[str, PromptProfile] = {
    "default": PromptProfile(
        id="default",
        system_prompt=SYSTEM_PROMPT_NAME,
        user_prompt=USER_PROMPT_NAME,
        json_template=DEFAULT_JSON_TEMPLATE,
        taxonomy_resource="default.json",
    ),
    "editorial": PromptProfile(
        id="editorial",
        system_prompt="editorial-system-prompt.txt",
        user_prompt="editorial-user-prompt.txt",
        json_template=EDITORIAL_JSON_TEMPLATE,
        taxonomy_resource="editorial.json",
    ),
}


def available_profiles() -> tuple[str, ...]:
    return tuple(PROMPT_PROFILES)


def resolve_profile(profile: str) -> PromptProfile:
    profile_id = (profile or "editorial").strip().lower()
    try:
        return PROMPT_PROFILES[profile_id]
    except KeyError as exc:
        available = ", ".join(available_profiles())
        raise CoreError(
            f"Unknown tagging style: {profile_id or '<empty>'}. "
            f"Available styles: {available}"
        ) from exc


@cache
def _read_resource_template(resource_name: str) -> str:
    text = (
        resources.files(PROMPT_PACKAGE)
        .joinpath(resource_name)
        .read_text(encoding="utf-8")
        .strip()
    )
    if not text:
        raise CoreError(f"Prompt template is empty: {resource_name}")
    return text


@cache
def _read_path_template(path_text: str) -> str:
    path = Path(path_text)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise CoreError(f"Prompt template is empty: {path}")
    return text


def read_template(path: Path | None = None, *, resource_name: str | None = None) -> str:
    try:
        if resource_name:
            return _read_resource_template(resource_name)
        elif path is not None:
            return _read_path_template(str(path))
        else:
            raise CoreError("Missing prompt template path")
    except FileNotFoundError as exc:
        raise CoreError(f"Prompt template not found: {resource_name or path}") from exc


def read_system_prompt(path: Path | None = None, *, profile: str = "editorial") -> str:
    if path is not None:
        return read_template(path)
    return read_template(resource_name=resolve_profile(profile).system_prompt)


def render_user_prompt(
    taxonomy: dict[str, list[str]],
    path: Path | None = None,
    *,
    profile: str = "editorial",
) -> str:
    prompt_profile = resolve_profile(profile)
    template = (
        read_template(path)
        if path is not None
        else read_template(resource_name=prompt_profile.user_prompt)
    )
    return (
        template.replace("{{json_template}}", prompt_profile.json_template)
        .replace("{{taxonomy}}", render_taxonomy_for_prompt(taxonomy))
        .replace("{{use_intents}}", render_use_intents_for_prompt())
    )
