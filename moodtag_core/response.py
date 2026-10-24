"""Assistant response extraction and moodtag JSON normalization."""

from __future__ import annotations

import json
import re
from typing import Any

from .contract import (
    ANNOTATION_FIELDS,
    COMMERCIAL_CONFIDENCE_VALUES,
    COMMERCIAL_LIST_FIELDS,
    CoreError,
    MoodtagAnalysis,
)
from .taxonomy import group_tags, reconcile_tags, reconcile_use_intents

MARKDOWN_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```")


def extract_assistant_content(data: Any) -> str:
    if not isinstance(data, dict):
        raise CoreError("Model response must be a JSON object")
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise CoreError("Model response is missing assistant message")
        refusal = message.get("refusal")
        if refusal:
            raise CoreError(f"Model refused image analysis: {str(refusal)[:300]}")
        content: Any = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {None, "text", "output_text"} and part.get(
                    "text"
                ):
                    parts.append(str(part["text"]))
            content = "\n".join(parts)
        if not isinstance(content, str) or not content.strip():
            raise CoreError("Model response has no assistant text")
        return content.strip()

    output = data.get("output")
    if not isinstance(output, list):
        raise CoreError("Model response is missing output text")
    parts: list[str] = []
    refused = ""
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("refusal"):
            refused = str(item["refusal"])
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal" and part.get("refusal"):
                refused = str(part["refusal"])
            if part.get("type") == "output_text" and part.get("text"):
                parts.append(str(part["text"]))
    if refused:
        raise CoreError(f"Model refused image analysis: {refused[:300]}")
    content = "\n".join(parts).strip()
    if not content:
        raise CoreError("Model response contains no output_text")
    return content


def parse_json_content(content: str) -> dict[str, Any]:
    candidate = content.strip().lstrip("\ufeff").strip()
    match = MARKDOWN_FENCE_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first == -1 or last <= first:
            raise CoreError(f"Model response is not JSON: {candidate[:500]}")
        candidate = candidate[first : last + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CoreError(f"Model returned invalid JSON: {candidate[:500]}") from exc
    if not isinstance(parsed, dict):
        raise CoreError("Model JSON response is not an object")
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
            raise CoreError(f"Model result missing required field: {field}")
        fields[field] = collapse_lines(value)

    raw_elements = data.get("elements", [])
    if not isinstance(raw_elements, list):
        raise CoreError("Model result field elements must be an array")
    elements = normalize_elements(raw_elements)
    if not elements:
        raise CoreError("Model result missing required field: elements")

    commercial_lists = {
        field: normalize_optional_list(data.get(field, []), field=field, maximum=10)
        for field in COMMERCIAL_LIST_FIELDS
    }
    commercial_format_confidence = normalize_commercial_confidence(
        data.get("commercial_format_confidence", "not_assessed")
    )

    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raise CoreError("Model result field tags must be an array")
    raw_use_intents = data.get("use_intents", [])
    if not isinstance(raw_use_intents, list):
        raise CoreError("Model result field use_intents must be an array")

    direct_tags = [str(value).strip() for value in raw_tags if str(value).strip()]
    intent_tags, use_intents, rejected_use_intents = reconcile_use_intents(
        [str(value).strip() for value in raw_use_intents if str(value).strip()]
    )
    # Validate the complete generated candidate set against this profile. This
    # keeps derived tags subject to the same taxonomy and count as direct tags.
    tags, rejected_tags = reconcile_tags(
        merge_unique(direct_tags, intent_tags), taxonomy, max_tags=max_tags
    )

    return MoodtagAnalysis(
        brief=fields["brief"],
        elements=elements,
        use=fields["use"],
        key=fields["key"],
        camera=fields["camera"],
        light_color=fields["light_color"],
        visible_text=commercial_lists["visible_text"],
        brand_evidence=commercial_lists["brand_evidence"],
        product_categories=commercial_lists["product_categories"],
        commercial_format_confidence=commercial_format_confidence,
        tags=tags,
        tag_groups=group_tags(tags, taxonomy),
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


def normalize_optional_list(values: Any, *, field: str, maximum: int) -> list[str]:
    if not isinstance(values, list):
        raise CoreError(f"Model result field {field} must be an array")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = collapse_lines(str(value)).strip().strip("。；;")
        if not clean or clean.lower() in seen:
            continue
        normalized.append(clean)
        seen.add(clean.lower())
        if len(normalized) >= maximum:
            break
    return normalized


def normalize_commercial_confidence(value: Any) -> str:
    if not isinstance(value, str):
        raise CoreError(
            "Model result field commercial_format_confidence must be a string"
        )
    confidence = value.strip().lower() or "not_assessed"
    if confidence not in COMMERCIAL_CONFIDENCE_VALUES:
        allowed = ", ".join(COMMERCIAL_CONFIDENCE_VALUES)
        raise CoreError(
            f"Model result field commercial_format_confidence must be one of: {allowed}"
        )
    return confidence


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
