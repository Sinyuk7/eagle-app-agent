from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

RESOURCE_PACKAGES = {
    "body-design.md": "moodboard_core.resources.specs",
}


@dataclass(frozen=True)
class MoodboardResource:
    name: str
    path: str
    content: str


def get_resource(name: str) -> MoodboardResource:
    package = RESOURCE_PACKAGES.get(name)
    if not package:
        available = ", ".join(sorted(RESOURCE_PACKAGES))
        raise ValueError(f"unknown resource: {name}; available: {available}")
    ref = resources.files(package).joinpath(name)
    return MoodboardResource(
        name=name,
        path=str(ref),
        content=ref.read_text(encoding="utf-8"),
    )
