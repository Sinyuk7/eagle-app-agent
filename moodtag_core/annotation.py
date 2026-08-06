"""Annotation formatting and detection for Eagle metadata."""

from __future__ import annotations

import re

from .contract import ANNOTATION_FIELDS, ANNOTATION_LABELS, MoodtagAnalysis

ANNOTATION_LABEL_ORDER = [ANNOTATION_LABELS[field] for field in ANNOTATION_FIELDS]
COMMERCIAL_ANNOTATION_LABEL_ORDER = [
    ANNOTATION_LABELS["visible_text"],
    ANNOTATION_LABELS["brand_evidence"],
    ANNOTATION_LABELS["product_categories"],
    ANNOTATION_LABELS["commercial_format_confidence"],
]
ALL_ANNOTATION_LABELS = ANNOTATION_LABEL_ORDER + COMMERCIAL_ANNOTATION_LABEL_ORDER


def build_annotation_block(analysis: MoodtagAnalysis) -> str:
    has_commercial_metadata = any(
        (
            analysis.visible_text,
            analysis.brand_evidence,
            analysis.product_categories,
            analysis.commercial_format_confidence != "not_assessed",
        )
    )
    values = {
        "Brief": analysis.brief,
        "Elements": format_elements(analysis.elements),
        "Use": analysis.use,
        "Key": analysis.key,
        "Camera": analysis.camera,
        "LightColor": analysis.light_color,
        "VisibleText": format_elements(analysis.visible_text),
        "BrandEvidence": format_elements(analysis.brand_evidence),
        "ProductCategories": format_elements(analysis.product_categories),
        "CommercialFormatConfidence": (
            analysis.commercial_format_confidence if has_commercial_metadata else ""
        ),
    }
    lines: list[str] = []
    for label in ALL_ANNOTATION_LABELS:
        value = values.get(label, "").strip()
        if value:
            lines.append(f"{label}: {value}")
            lines.append("")
    return "\n".join(lines).strip()


def has_analysis_annotation(annotation: str) -> bool:
    fields = parse_annotation_fields(annotation)
    return all(fields.get(label) for label in ANNOTATION_LABEL_ORDER)


def replace_analysis_annotation(existing: str, block: str) -> str:
    existing = existing or ""
    span = find_analysis_span(existing)
    if span:
        start, end = span
        return (
            existing[:start].rstrip()
            + "\n\n"
            + block
            + "\n\n"
            + existing[end:].lstrip()
        ).strip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + block
    return block


def remove_analysis_annotation(existing: str) -> str:
    span = find_analysis_span(existing or "")
    if not span:
        return (existing or "").strip()
    start, end = span
    return (
        (existing or "")[:start].rstrip() + "\n\n" + (existing or "")[end:].lstrip()
    ).strip()


def extract_brief(annotation: str) -> str:
    return parse_annotation_fields(annotation).get("Brief", "")


def parse_annotation_fields(annotation: str) -> dict[str, str]:
    text = annotation or ""
    result: dict[str, str] = {}
    matches = list(label_matches(text))
    labels = set(ALL_ANNOTATION_LABELS)
    for index, match in enumerate(matches):
        label = match.group(1)
        if label not in labels:
            continue
        value_start = match.end()
        value_end = len(text)
        for next_match in matches[index + 1 :]:
            if next_match.group(1) in labels:
                value_end = next_match.start()
                break
        value = text[value_start:value_end].strip()
        if value:
            result[label] = collapse_blank_lines(value)
    return result


def find_analysis_span(annotation: str) -> tuple[int, int] | None:
    text = annotation or ""
    matches = [
        match
        for match in label_matches(text)
        if match.group(1) in ALL_ANNOTATION_LABELS
    ]
    if not matches:
        return None
    present = {match.group(1) for match in matches}
    if not all(label in present for label in ANNOTATION_LABEL_ORDER):
        return None
    start = min(match.start() for match in matches)
    end = len(text)
    last = max(matches, key=lambda match: match.start())
    after_last = text[last.end() :]
    boundary = re.search(
        r"\n\s*\n(?!\s*(?:Brief|Elements|Use|Key|Camera|LightColor|VisibleText|"
        r"BrandEvidence|ProductCategories|CommercialFormatConfidence):)",
        after_last,
    )
    if boundary:
        end = last.end() + boundary.start()
    return start, end


def label_matches(text: str) -> list[re.Match[str]]:
    return list(
        re.finditer(
            r"(?m)^(Brief|Elements|Use|Key|Camera|LightColor|VisibleText|"
            r"BrandEvidence|ProductCategories|CommercialFormatConfidence):\s*",
            text or "",
        )
    )


def collapse_blank_lines(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def format_elements(elements: list[str]) -> str:
    clean = [element.strip().rstrip("。；;") for element in elements if element.strip()]
    if not clean:
        return ""
    return "；".join(clean) + "。"
