"""Shared strict Moodtag output schema and lightweight validation."""

from __future__ import annotations

from typing import Any

from .contract import (
    ANNOTATION_FIELDS,
    COMMERCIAL_CONFIDENCE_VALUES,
    COMMERCIAL_LIST_FIELDS,
    CoreError,
)


def moodtag_json_schema(profile: str = "editorial") -> dict[str, Any]:
    """Return Ollama's structured-output schema for the current analysis contract."""
    properties: dict[str, Any] = {
        "brief": {"type": "string"},
        "elements": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "use": {"type": "string"},
        "key": {"type": "string"},
        "camera": {"type": "string"},
        "light_color": {"type": "string"},
        "suggest_title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "use_intents": {"type": "array", "items": {"type": "string"}},
    }
    required = [*ANNOTATION_FIELDS, "suggest_title", "tags", "use_intents"]
    if profile == "editorial":
        properties.update(
            {
                field: {"type": "array", "items": {"type": "string"}}
                for field in COMMERCIAL_LIST_FIELDS
            }
        )
        properties["commercial_format_confidence"] = {
            "type": "string",
            "enum": list(COMMERCIAL_CONFIDENCE_VALUES),
        }
        required.extend([*COMMERCIAL_LIST_FIELDS, "commercial_format_confidence"])
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


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
