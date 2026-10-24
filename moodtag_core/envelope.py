"""Provider response envelopes that keep transport metadata out of the domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ResponseMetadata:
    protocol: str
    model: str
    response_id: str | None = None
    request_id: str | None = None
    client_request_id: str | None = None
    status: str | None = None
    http_status: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: int | None = None


@dataclass(frozen=True)
class ResponseEnvelope(Generic[T]):
    data: T
    metadata: ResponseMetadata


def normalize_usage(usage: Any) -> dict[str, int]:
    """Return common token counters without inventing missing values."""
    if not isinstance(usage, dict):
        return {}
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
        "reasoning_tokens": ("reasoning_tokens",),
        "cached_tokens": ("cached_tokens", "input_cached_tokens"),
        "cache_write_tokens": ("cache_write_tokens",),
    }
    normalized: dict[str, int] = {}
    for target, keys in aliases.items():
        for key in keys:
            value = usage.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float) and value >= 0:
                normalized[target] = int(value)
                break
    input_details = usage.get("input_tokens_details")
    if isinstance(input_details, dict):
        cached = input_details.get("cached_tokens")
        if isinstance(cached, int | float) and not isinstance(cached, bool):
            normalized["cached_tokens"] = int(cached)
        cache_write = input_details.get("cache_write_tokens")
        if isinstance(cache_write, int | float) and not isinstance(cache_write, bool):
            normalized["cache_write_tokens"] = int(cache_write)
    output_details = usage.get("output_tokens_details")
    if isinstance(output_details, dict):
        reasoning = output_details.get("reasoning_tokens")
        if isinstance(reasoning, int | float) and not isinstance(reasoning, bool):
            normalized["reasoning_tokens"] = int(reasoning)
    return normalized


def estimate_cost(
    usage: Any,
    *,
    input_per_million: float | None = None,
    output_per_million: float | None = None,
    cached_per_million: float | None = None,
) -> float | None:
    """Estimate cost only when all required prices are explicitly configured."""
    normalized = normalize_usage(usage)
    if input_per_million is None or output_per_million is None:
        return None
    input_tokens = normalized.get("input_tokens")
    output_tokens = normalized.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    input_rate = (
        cached_per_million if cached_per_million is not None else input_per_million
    )
    cached_tokens = normalized.get("cached_tokens", 0)
    regular_input = max(0, input_tokens - cached_tokens)
    return (
        regular_input * input_per_million
        + cached_tokens * input_rate
        + output_tokens * output_per_million
    ) / 1_000_000
