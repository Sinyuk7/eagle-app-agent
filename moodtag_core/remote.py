"""Remote OpenAI-compatible Chat and Responses vision client."""

from __future__ import annotations

import random
import time
import urllib.parse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .catalog import catalog_entry_for_model
from .common import (
    CoreError,
    ProviderAttempt,
    ProviderAuthenticationError,
    ProviderEndpoint,
    ProviderHTTPError,
    ProviderNetworkError,
    elapsed_ms_since,
    file_to_data_url,
    http_request_with_metadata,
    normalize_base_url,
    normalize_response_headers,
    redact,
    validate_protocol,
)
from .contract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    MoodtagAnalysis,
)
from .envelope import ResponseEnvelope, ResponseMetadata
from .prompts import (
    read_system_prompt,
    render_item_context,
    render_user_prompt,
    resolve_profile,
)
from .response import parse_analysis_response
from .schema import moodtag_json_schema

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_SUCCESS_FINISH_REASONS = {"stop", "tool_calls", "function_call"}
_SCHEMA_NAME = "moodtag_analysis"
_IMAGE_DETAIL = "auto"


def _is_official_openai_endpoint(base_url: str) -> bool:
    return urllib.parse.urlsplit(base_url).hostname == "api.openai.com"


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return max(0.0, (date - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _response_status_error(data: Any, protocol: str) -> str | None:
    if not isinstance(data, dict):
        return None
    if protocol == "responses":
        status = data.get("status")
        if status != "completed":
            detail = data.get("incomplete_details") or data.get("error") or status
            return f"Responses request did not complete ({status or 'missing status'}): {str(detail)[:500]}"
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0] if isinstance(choices[0], dict) else {}
    reason = choice.get("finish_reason")
    if reason and reason not in _SUCCESS_FINISH_REASONS:
        return f"Chat completion ended with finish_reason={reason}"
    return None


class VisionClient:
    def __init__(
        self,
        *,
        protocol: str,
        base_url: str,
        model: str,
        api_key: str | None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        profile: str = "editorial",
    ) -> None:
        self.protocol = validate_protocol(protocol)
        self.base_url = normalize_base_url(base_url, self.protocol)
        self.model = str(model or "").strip()
        self.api_key = api_key
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.profile = resolve_profile(profile).id
        entry = catalog_entry_for_model(self.model)
        self.explicit_prompt_cache = bool(
            entry
            and entry.explicit_prompt_cache
            and _is_official_openai_endpoint(self.base_url)
        )
        self.last_endpoint_protocol = self.protocol
        self.last_endpoint_base_url = self.base_url
        self.last_endpoint_model = self.model
        self.last_attempts: list[ProviderAttempt] = []
        self.last_response: ResponseEnvelope[MoodtagAnalysis] | None = None

    def base_urls(self) -> list[str]:
        return [self.base_url]

    def endpoint(self) -> ProviderEndpoint:
        return ProviderEndpoint(self.protocol, self.base_url, self.api_key, self.model)

    def build_payload(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        *,
        original_title: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        system = read_system_prompt(profile=self.profile)
        prompt = render_user_prompt(taxonomy, profile=self.profile)
        item_context = render_item_context(original_title, source_url)
        dynamic_prompt = f"{prompt}{item_context}"
        if self.protocol == "chat":
            if self.explicit_prompt_cache:
                stable = f"{system}\n\n{prompt}"
                messages = [
                    {
                        "role": "developer",
                        "content": [
                            {
                                "type": "text",
                                "text": stable,
                                "prompt_cache_breakpoint": {"mode": "explicit"},
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Analyze this image.{item_context}",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": file_to_data_url(image, "image/jpeg"),
                                    "detail": _IMAGE_DETAIL,
                                },
                            },
                        ],
                    },
                ]
            else:
                messages = [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": dynamic_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": file_to_data_url(image, "image/jpeg"),
                                    "detail": _IMAGE_DETAIL,
                                },
                            },
                        ],
                    },
                ]
            payload: dict[str, Any] = {
                "model": self.model,
                "store": False,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "messages": messages,
            }
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _SCHEMA_NAME,
                    "strict": True,
                    "schema": moodtag_json_schema(self.profile),
                },
            }
            if self.explicit_prompt_cache:
                payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
            return payload

        if self.explicit_prompt_cache:
            stable = f"{system}\n\n{prompt}"
            input_items = [
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": stable,
                            "prompt_cache_breakpoint": {"mode": "explicit"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Analyze this image.{item_context}",
                        },
                        {
                            "type": "input_image",
                            "image_url": file_to_data_url(image, "image/jpeg"),
                            "detail": _IMAGE_DETAIL,
                        },
                    ],
                },
            ]
        else:
            input_items = [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": dynamic_prompt},
                        {
                            "type": "input_image",
                            "image_url": file_to_data_url(image, "image/jpeg"),
                            "detail": _IMAGE_DETAIL,
                        },
                    ],
                },
            ]
        payload = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "low"},
            "input": input_items,
        }
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": _SCHEMA_NAME,
                "strict": True,
                "schema": moodtag_json_schema(self.profile),
            }
        }
        if self.explicit_prompt_cache:
            payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
        return payload

    def analyze(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        retries: int,
        max_tags: int,
        *,
        original_title: str = "",
        source_url: str = "",
    ) -> MoodtagAnalysis:
        return self.analyze_envelope(
            image,
            taxonomy,
            retries,
            max_tags,
            original_title=original_title,
            source_url=source_url,
        ).data

    def analyze_envelope(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        retries: int,
        max_tags: int,
        *,
        original_title: str = "",
        source_url: str = "",
    ) -> ResponseEnvelope[MoodtagAnalysis]:
        self.last_attempts = []
        endpoint = self.endpoint()
        if not endpoint.api_key:
            error = CoreError("Missing API key")
            self._record_attempt(endpoint, ok=False, error=error)
            raise CoreError("Missing API key. Run moodtag config model.")
        if not endpoint.model:
            error = CoreError("Missing model")
            self._record_attempt(endpoint, ok=False, error=error)
            raise CoreError("Missing model. Run moodtag config model.")
        try:
            payload = self.build_payload(
                image, taxonomy, original_title=original_title, source_url=source_url
            )
        except CoreError as exc:
            self._record_attempt(endpoint, ok=False, error=exc)
            raise
        last_error: Exception | None = None
        started_total = time.monotonic()
        for attempt in range(retries + 1):
            started = time.monotonic()
            client_request_id = (
                uuid4().hex if _is_official_openai_endpoint(endpoint.base_url) else None
            )
            request_headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {endpoint.api_key}",
            }
            if client_request_id:
                request_headers["X-Client-Request-Id"] = client_request_id
            try:
                response = http_request_with_metadata(
                    "POST",
                    endpoint.url,
                    headers=request_headers,
                    json_body=payload,
                    timeout=180,
                    secret=endpoint.api_key,
                )
                status_error = _response_status_error(response.data, endpoint.protocol)
                if status_error:
                    raise CoreError(status_error)
                result = parse_analysis_response(
                    response.data, taxonomy, max_tags=max_tags
                )
            except ProviderHTTPError as exc:
                last_error = exc
                self._record_attempt(
                    endpoint,
                    ok=False,
                    error=exc,
                    elapsed_ms=elapsed_ms_since(started),
                    status=exc.status,
                    submission_state="response_received",
                    client_request_id=client_request_id,
                    headers=exc.headers,
                )
                if exc.status in {401, 403}:
                    raise ProviderAuthenticationError(endpoint, exc) from exc
                if exc.status not in _RETRYABLE_STATUS_CODES:
                    raise
                if attempt >= retries:
                    break
                self._sleep_before_retry(attempt, exc.headers.get("retry-after"))
                continue
            except ProviderNetworkError as exc:
                last_error = exc
                self._record_attempt(
                    endpoint,
                    ok=False,
                    error=exc,
                    elapsed_ms=elapsed_ms_since(started),
                    submission_state="unknown",
                    client_request_id=client_request_id,
                )
                break
            except CoreError as exc:
                last_error = exc
                self._record_attempt(
                    endpoint,
                    ok=False,
                    error=exc,
                    elapsed_ms=elapsed_ms_since(started),
                    submission_state="response_received",
                    client_request_id=client_request_id,
                )
                raise
            else:
                data = response.data
                response_headers = normalize_response_headers(response.headers)
                envelope = ResponseEnvelope(
                    data=result,
                    metadata=ResponseMetadata(
                        protocol=endpoint.protocol,
                        model=endpoint.model,
                        response_id=(
                            data.get("id")
                            if isinstance(data, dict)
                            and isinstance(data.get("id"), str)
                            else None
                        ),
                        request_id=(
                            response_headers.get("x-request-id")
                            or response_headers.get("request-id")
                        ),
                        client_request_id=client_request_id,
                        status=(
                            data.get("status")
                            if isinstance(data, dict)
                            and isinstance(data.get("status"), str)
                            else None
                        ),
                        http_status=response.status,
                        usage=(
                            data.get("usage", {})
                            if isinstance(data, dict)
                            and isinstance(data.get("usage", {}), dict)
                            else {}
                        ),
                        headers=response_headers,
                        elapsed_ms=elapsed_ms_since(started_total),
                    ),
                )
                self.last_response = envelope
                self._record_attempt(
                    endpoint,
                    ok=True,
                    elapsed_ms=elapsed_ms_since(started),
                    status=response.status,
                    submission_state="response_received",
                    client_request_id=client_request_id,
                    headers=response_headers,
                )
                self.last_endpoint_protocol = endpoint.protocol
                self.last_endpoint_base_url = endpoint.base_url
                self.last_endpoint_model = endpoint.model
                return envelope
        failure = CoreError(
            f"Model request failed: {redact(str(last_error), endpoint.api_key)}"
        )
        failure.attempts = tuple(self.last_attempts)  # type: ignore[attr-defined]
        raise failure

    @staticmethod
    def _sleep_before_retry(attempt: int, retry_after: str | None) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = min(30.0, 1.5 * (2**attempt)) + random.uniform(0, 0.25)
        time.sleep(delay)

    def _record_attempt(
        self,
        endpoint: ProviderEndpoint,
        *,
        ok: bool,
        elapsed_ms: int = 0,
        error: Exception | None = None,
        status: int | None = None,
        submission_state: str = "not_sent",
        client_request_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.last_attempts.append(
            ProviderAttempt(
                protocol=endpoint.protocol,
                base_url=endpoint.base_url,
                model=endpoint.model,
                ok=ok,
                elapsed_ms=elapsed_ms,
                status=(
                    status
                    if status is not None
                    else error.status
                    if isinstance(error, ProviderHTTPError)
                    else None
                ),
                error=redact(str(error), endpoint.api_key)[:500] if error else "",
                submission_state=submission_state,
                client_request_id=client_request_id,
                headers=headers or {},
            )
        )


OLLAMA_PRESETS: dict[str, dict[str, Any]] = {
    "smoke": {"temperature": 0, "think": False},
    "qwen-instruct": {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1,
        "think": False,
    },
    "mlx-default": {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1,
        "think": False,
    },
}
