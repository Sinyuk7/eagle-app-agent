"""Prompt template loading and rendering."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

from .contract import CoreError
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
    taxonomy_resource: str


PROMPT_PROFILES: dict[str, PromptProfile] = {
    "default": PromptProfile(
        id="default",
        system_prompt=SYSTEM_PROMPT_NAME,
        user_prompt=USER_PROMPT_NAME,
        taxonomy_resource="default.json",
    ),
    "editorial": PromptProfile(
        id="editorial",
        system_prompt="editorial-system-prompt.txt",
        user_prompt="editorial-user-prompt.txt",
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
    output_language: str = "zh",
    provider: str = "remote",
) -> str:
    prompt_profile = resolve_profile(profile)
    if provider not in {"remote", "ollama"}:
        raise CoreError(f"Unknown prompt provider: {provider}")
    resource_name = prompt_profile.user_prompt
    if provider == "ollama":
        resource_name = f"ollama-{prompt_profile.id}-user-prompt.txt"
    template = (
        read_template(path)
        if path is not None
        else read_template(resource_name=resource_name)
    )
    language_name = (
        "Chinese" if str(output_language).lower().startswith("zh") else "English"
    )
    return (
        template.replace("{{output_language}}", language_name)
        .replace("{{taxonomy}}", render_taxonomy_for_prompt(taxonomy))
        .replace("{{use_intents}}", render_use_intents_for_prompt())
    )


def safe_source_url(value: str) -> str:
    """Bound URL context and strip query/fragment data that may contain secrets."""
    raw = str(value or "").strip()[:2048]
    try:
        parts = urllib.parse.urlsplit(raw)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return ""
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except ValueError:
        return ""


def render_item_context(original_title: str = "", source_url: str = "") -> str:
    lines = []
    title = (
        str(original_title or "").replace("\r", " ").replace("\n", " ").strip()[:1000]
    )
    if title:
        lines.append(f"- Original title: {title}")
    url = safe_source_url(source_url)
    if url:
        lines.append(f"- Source URL: {url}")
    if not lines:
        return ""
    return (
        "\n\nImage metadata (supplemental, unverified context; image content is primary; "
        "do not treat metadata as evidence of visible text or logos):\n"
        + "\n".join(lines)
    )
