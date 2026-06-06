"""Taxonomy loading, rendering, and tag reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

from .contract import CoreError, USE_INTENT_TAGS


def load_taxonomy(path: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CoreError(f"Taxonomy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CoreError(f"Invalid taxonomy JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CoreError("Taxonomy must be a JSON object")
    taxonomy: dict[str, list[str]] = {}
    for group, tags in data.items():
        if not isinstance(tags, list):
            continue
        clean = [str(tag).strip() for tag in tags if str(tag).strip()]
        if clean:
            taxonomy[str(group)] = clean
    if not taxonomy:
        raise CoreError("Taxonomy has no usable tags")
    return taxonomy


def flatten_taxonomy(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for tags in taxonomy.values():
        for tag in tags:
            allowed[tag.lower()] = tag
    return allowed


def render_taxonomy_for_prompt(taxonomy: dict[str, list[str]]) -> str:
    return "\n".join(
        f"{group}: {' | '.join(tags)}" for group, tags in taxonomy.items()
    )


def render_use_intents_for_prompt() -> str:
    return "\n".join(f"{intent} -> {tag}" for intent, tag in USE_INTENT_TAGS.items())


def reconcile_tags(
    tags: list[str], taxonomy: dict[str, list[str]], max_tags: int
) -> tuple[list[str], list[str]]:
    allowed = flatten_taxonomy(taxonomy)
    resolved: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw).strip()
        canonical = allowed.get(tag.lower())
        if canonical and canonical.lower() not in seen:
            resolved.append(canonical)
            seen.add(canonical.lower())
        elif tag and tag.lower() not in {value.lower() for value in rejected}:
            rejected.append(tag)
    return resolved[:max_tags], rejected


def reconcile_use_intents(use_intents: list[str]) -> tuple[list[str], list[str], list[str]]:
    resolved_tags: list[str] = []
    accepted: list[str] = []
    rejected: list[str] = []
    seen_tags: set[str] = set()
    seen_intents: set[str] = set()
    for raw in use_intents:
        intent = str(raw).strip()
        tag = USE_INTENT_TAGS.get(intent)
        if tag:
            if intent not in seen_intents:
                accepted.append(intent)
                seen_intents.add(intent)
            if tag.lower() not in seen_tags:
                resolved_tags.append(tag)
                seen_tags.add(tag.lower())
        elif intent and intent.lower() not in {value.lower() for value in rejected}:
            rejected.append(intent)
    return resolved_tags, accepted, rejected

