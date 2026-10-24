"""Taxonomy loading, rendering, and tag reconciliation."""

from __future__ import annotations

import json
from importlib import resources

from .contract import USE_INTENT_TAGS, CoreError

TAXONOMY_PACKAGE = "moodtag_core.resources.taxonomy"


def load_profile_taxonomy(profile: str = "editorial") -> dict[str, list[str]]:
    """Load bundled taxonomy selected by the prompt profile."""
    from .prompts import resolve_profile

    prompt_profile = resolve_profile(profile)
    resource_name = prompt_profile.taxonomy_resource
    try:
        text = (
            resources.files(TAXONOMY_PACKAGE)
            .joinpath(resource_name)
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise CoreError(f"Taxonomy resource not found: {resource_name}") from exc
    return parse_taxonomy_json(text, label=resource_name)


def parse_taxonomy_json(text: str, *, label: str) -> dict[str, list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CoreError(f"Invalid taxonomy JSON: {label}: {exc}") from exc
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
    validate_unique_tags(taxonomy)
    return taxonomy


def flatten_taxonomy(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    validate_unique_tags(taxonomy)
    allowed: dict[str, str] = {}
    for tags in taxonomy.values():
        for tag in tags:
            allowed[tag.lower()] = tag
    return allowed


def group_tags(tags: list[str], taxonomy: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return canonical tags grouped by their taxonomy facet."""
    grouped: dict[str, list[str]] = {}
    for group, values in taxonomy.items():
        canonical = {value.lower(): value for value in values}
        matched = [canonical[tag.lower()] for tag in tags if tag.lower() in canonical]
        if matched:
            grouped[group] = matched
    return grouped


def validate_unique_tags(taxonomy: dict[str, list[str]]) -> None:
    """Reject cross-facet duplicate labels before flattening loses their meaning."""
    groups_by_tag: dict[str, str] = {}
    for group, tags in taxonomy.items():
        for tag in tags:
            key = tag.lower()
            previous = groups_by_tag.get(key)
            if previous is not None and previous != group:
                raise CoreError(
                    f"Taxonomy tag {tag!r} appears in both {previous!r} and {group!r}"
                )
            if previous == group:
                raise CoreError(
                    f"Taxonomy tag {tag!r} appears more than once in {group!r}"
                )
            groups_by_tag[key] = group


def render_taxonomy_for_prompt(taxonomy: dict[str, list[str]]) -> str:
    return "\n".join(f"{group}: {' | '.join(tags)}" for group, tags in taxonomy.items())


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
        elif canonical:
            # A valid canonical tag already accepted above is a duplicate.
            continue
        elif tag and tag.lower() not in {value.lower() for value in rejected}:
            rejected.append(tag)
    return resolved[:max_tags], rejected


def reconcile_use_intents(
    use_intents: list[str],
) -> tuple[list[str], list[str], list[str]]:
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
