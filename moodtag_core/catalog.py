"""Fixed, packaged model choices and their request protocols."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from .contract import CoreError


@dataclass(frozen=True)
class ModelCatalogEntry:
    id: str
    name: str
    protocol: str
    recommended: bool = False


_RESOURCE_PROTOCOLS = {"chat.json": "chat", "responses.json": "responses"}


def load_model_catalog() -> tuple[ModelCatalogEntry, ...]:
    entries: list[ModelCatalogEntry] = []
    seen: set[str] = set()
    for resource, protocol in _RESOURCE_PROTOCOLS.items():
        try:
            raw = (
                files("moodtag_core.resources.models")
                .joinpath(resource)
                .read_text(encoding="utf-8")
            )
            values = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise CoreError(f"Invalid bundled model catalog: {resource}") from exc
        if not isinstance(values, list) or not values:
            raise CoreError(f"Model catalog {resource} must be a non-empty list")
        recommended = 0
        for value in values:
            if not isinstance(value, dict):
                raise CoreError(f"Model catalog {resource} contains an invalid entry")
            model_id = str(value.get("id") or "").strip()
            name = str(value.get("name") or model_id).strip()
            marker = value.get("recommended", False)
            if not model_id or not name or not isinstance(marker, bool):
                raise CoreError(f"Model catalog {resource} contains an invalid entry")
            if model_id in seen:
                raise CoreError(f"Model catalog contains duplicate ID: {model_id}")
            seen.add(model_id)
            recommended += int(marker)
            entries.append(ModelCatalogEntry(model_id, name, protocol, marker))
        if recommended > 1:
            raise CoreError(f"Model catalog {resource} has multiple recommended models")
    return tuple(entries)


def models_for_protocol(protocol: str) -> tuple[ModelCatalogEntry, ...]:
    return tuple(entry for entry in load_model_catalog() if entry.protocol == protocol)


def protocol_for_model(model: str) -> str:
    value = str(model or "").strip()
    for entry in load_model_catalog():
        if entry.id == value:
            return entry.protocol
    raise CoreError(
        f"Unsupported model: {value or '-'}; run `moodtag config model` to select a supported model"
    )
