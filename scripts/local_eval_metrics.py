"""Maintainer-only metrics for local Ollama evaluation reports."""

from __future__ import annotations

import re
from typing import Any


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def score_item(analysis: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    values: list[str] = []
    for field in (
        "brief",
        "elements",
        "use",
        "key",
        "camera",
        "light_color",
        "visible_text",
        "brand_evidence",
        "product_categories",
    ):
        raw = analysis.get(field, [])
        values.extend(
            _norm(item)
            for item in (raw if isinstance(raw, list) else [raw])
            if _norm(item)
        )
    facts = [_norm(item) for item in gold.get("visible_facts", []) if _norm(item)]
    variants = {
        _norm(key): [_norm(item) for item in items if _norm(item)]
        for key, items in gold.get("acceptable_variants", {}).items()
        if isinstance(items, list)
    }
    matched = sum(
        any(fact in text for text in values)
        or any(item in text for item in variants.get(fact, []) for text in values)
        for fact in facts
    )
    unsupported = sum(
        any(_norm(claim) in text for text in values)
        for claim in gold.get("disallowed_claims", [])
    )
    expected = {_norm(item) for item in gold.get("tags", []) if _norm(item)}
    predicted = [_norm(item) for item in analysis.get("tags", []) if _norm(item)]
    predicted_set = set(predicted)
    true_positive = len(expected & predicted_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = (
        true_positive / len(expected)
        if expected
        else (1.0 if not predicted_set else 0.0)
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "matched_facts": matched,
        "fact_count": len(facts),
        "unsupported_claim_count": unsupported,
        "tag_precision": precision,
        "tag_recall": recall,
        "tag_f1": f1,
        "rejected_tag_count": len(analysis.get("rejected_tags", [])),
        "duplicate_tag_count": len(predicted) - len(predicted_set),
        "useful_field_count": sum(
            bool(analysis.get(field))
            for field in ("brief", "elements", "use", "key", "camera", "light_color")
        ),
    }


def _percentile(values: list[int], percent: float) -> int | None:
    if not values:
        return None
    return sorted(values)[
        max(0, min(len(values) - 1, round(len(values) * percent / 100) - 1))
    ]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [item["metrics"] for item in records if item.get("metrics")]
    latencies = [
        int(item["elapsed_ms"])
        for item in records
        if item.get("elapsed_ms") is not None
    ]
    return {
        "sample_count": len(records),
        "contract_pass_rate": sum(bool(item.get("ok")) for item in records)
        / len(records)
        if records
        else 0.0,
        "unsupported_claims": sum(item["unsupported_claim_count"] for item in scored),
        "tag_precision": sum(item["tag_precision"] for item in scored) / len(scored)
        if scored
        else None,
        "tag_recall": sum(item["tag_recall"] for item in scored) / len(scored)
        if scored
        else None,
        "tag_f1": sum(item["tag_f1"] for item in scored) / len(scored)
        if scored
        else None,
        "rejected_tags": sum(item["rejected_tag_count"] for item in scored),
        "duplicate_tags": sum(item["duplicate_tag_count"] for item in scored),
        "latency_ms": {
            "p50_descriptive": _percentile(latencies, 50),
            "p95_descriptive": _percentile(latencies, 95),
        },
    }
