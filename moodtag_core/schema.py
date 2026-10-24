"""Shared strict Moodtag output schema and lightweight validation."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from .contract import (
    CoreError,
)


@cache
def _read_schema_resource(profile: str) -> dict[str, Any]:
    if profile not in {"default", "editorial"}:
        raise CoreError(f"Unknown schema profile: {profile}")
    resource = resources.files("moodtag_core.resources.schemas").joinpath(
        f"{profile}.json"
    )
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise CoreError(f"Invalid schema resource: {profile}") from exc
    if not isinstance(value, dict):
        raise CoreError(f"Invalid schema resource: {profile}")
    return value


def moodtag_json_schema(profile: str = "editorial") -> dict[str, Any]:
    """Load the shared profile-specific structured-output schema resource."""
    return json.loads(json.dumps(_read_schema_resource(profile)))


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate the emitted contract subset without adding a runtime dependency."""
    expected = schema.get("type")
    valid = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
    }
    if expected in valid and not valid[expected](value):
        raise CoreError(
            f"Ollama schema validation failed at {path}: expected {expected}"
        )
    if "enum" in schema and value not in schema["enum"]:
        raise CoreError(f"Ollama schema validation failed at {path}: invalid value")
    if expected == "object":
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise CoreError(
                f"Ollama schema validation failed at {path}: missing required fields"
            )
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise CoreError(
                f"Ollama schema validation failed at {path}: unexpected fields"
            )
        for key, child in value.items():
            if key in properties:
                validate_json_schema(child, properties[key], f"{path}.{key}")
    if expected == "array":
        if len(value) < schema.get("minItems", 0):
            raise CoreError(f"Ollama schema validation failed at {path}: too few items")
        for index, child in enumerate(value):
            validate_json_schema(child, schema.get("items", {}), f"{path}[{index}]")
