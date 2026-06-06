"""Assistant response extraction and moodtag JSON normalization."""

from __future__ import annotations

import json
import re
from typing import Any

from .contract import ANNOTATION_FIELDS, CoreError, MoodtagAnalysis
from .taxonomy import reconcile_tags, reconcile_use_intents

MARKDOWN_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```")


def extract_assistant_content(data: Any) -> str:
    content: Any = None
    if isinstance(data, dict):
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = data.get("output_text")
    if isinstance(content, list):
        content = "\n".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise CoreError("Could not extract assistant content from provider response")
    return content.strip()


def parse_json_content(content: str) -> dict[str, Any]:
    candidate = content.strip().lstrip("\ufeff").strip()
    match = MARKDOWN_FENCE_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first == -1 or last <= first:
            raise CoreError(f"VL response is not JSON: {candidate[:500]}")
        candidate = candidate[first : last + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CoreError(f"VL returned invalid JSON: {candidate[:500]}") from exc
    if not isinstance(parsed, dict):
        raise CoreError("VL JSON response is not an object")
    return parsed


def parse_analysis_response(
    data: Any, taxonomy: dict[str, list[str]], max_tags: int
) -> MoodtagAnalysis:
    return normalize_analysis_json(
        parse_json_content(extract_assistant_content(data)),
        taxonomy=taxonomy,
        max_tags=max_tags,
    )


def normalize_analysis_json(
    data: dict[str, Any], *, taxonomy: dict[str, list[str]], max_tags: int
) -> MoodtagAnalysis:
    data = normalize_contract_aliases(data)
    fields: dict[str, str] = {}
    for field in ANNOTATION_FIELDS:
        if field == "elements":
            continue
        value = data.get(field, "")
        if not isinstance(value, str) or not value.strip():
            raise CoreError(f"VL result missing required field: {field}")
        fields[field] = collapse_lines(value)

    raw_elements = data.get("elements", [])
    if not isinstance(raw_elements, list):
        raise CoreError("VL result field elements must be an array")
    elements = normalize_elements(raw_elements)
    if not elements:
        raise CoreError("VL result missing required field: elements")

    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raise CoreError("VL result field tags must be an array")
    raw_use_intents = data.get("use_intents", [])
    if not isinstance(raw_use_intents, list):
        raise CoreError("VL result field use_intents must be an array")

    tags, rejected_tags = reconcile_tags(
        [str(value).strip() for value in raw_tags if str(value).strip()],
        taxonomy,
        max_tags=max_tags,
    )
    intent_tags, use_intents, rejected_use_intents = reconcile_use_intents(
        [str(value).strip() for value in raw_use_intents if str(value).strip()]
    )
    tags = merge_unique(tags, intent_tags)[:max_tags]

    return MoodtagAnalysis(
        brief=fields["brief"],
        elements=elements,
        use=fields["use"],
        key=fields["key"],
        camera=fields["camera"],
        light_color=fields["light_color"],
        tags=tags,
        use_intents=use_intents,
        rejected_tags=rejected_tags,
        rejected_use_intents=rejected_use_intents,
    )


def normalize_contract_aliases(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "light_color" not in normalized:
        for alias in ("lightColor", "lightcolor", "light_coloring", "lightColour"):
            if alias in normalized:
                normalized["light_color"] = normalized[alias]
                break
    return normalized


def normalize_elements(values: list[Any]) -> list[str]:
    elements: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = collapse_lines(str(value)).strip().strip("。；;")
        if not clean or clean.lower() in seen:
            continue
        elements.append(clean)
        seen.add(clean.lower())
        if len(elements) >= 10:
            break
    return elements


def collapse_lines(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def merge_unique(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in first + second:
        clean = value.strip()
        if clean and clean.lower() not in seen:
            out.append(clean)
            seen.add(clean.lower())
    return out
