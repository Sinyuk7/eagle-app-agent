"""Remote OpenAI-compatible Chat and Responses vision client."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .common import (
    CoreError,
    ProviderAttempt,
    ProviderAuthenticationError,
    ProviderEndpoint,
    ProviderHTTPError,
    ProviderNetworkError,
    elapsed_ms_since,
    file_to_data_url,
    http_request,
    normalize_base_url,
    redact,
    validate_protocol,
)
from .contract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    MoodtagAnalysis,
)
from .prompts import read_system_prompt, render_user_prompt, resolve_profile
from .response import parse_analysis_response


class VisionClient:
    def __init__(
        self,
        *,
        protocol: str,
        base_url: str,
        model: str,
        api_key: str | None,
        response_format: bool = not DEFAULT_NO_RESPONSE_FORMAT,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        profile: str = "editorial",
    ) -> None:
        self.protocol = validate_protocol(protocol)
        self.base_url = normalize_base_url(base_url, self.protocol)
        self.model = str(model or "").strip()
        self.api_key = api_key
        self.response_format = response_format
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.profile = resolve_profile(profile).id
        self.last_endpoint_protocol = self.protocol
        self.last_endpoint_base_url = self.base_url
        self.last_endpoint_model = self.model
        self.last_attempts: list[ProviderAttempt] = []

    def base_urls(self) -> list[str]:
        return [self.base_url]

    def endpoint(self) -> ProviderEndpoint:
        return ProviderEndpoint(self.protocol, self.base_url, self.api_key, self.model)

    def build_payload(
        self, image: Path, taxonomy: dict[str, list[str]]
    ) -> dict[str, Any]:
        system = read_system_prompt(profile=self.profile)
        prompt = render_user_prompt(taxonomy, profile=self.profile)
        if self.protocol == "chat":
            payload: dict[str, Any] = {
                "model": self.model,
                "store": False,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": file_to_data_url(image, "image/jpeg")
                                },
                            },
                        ],
                    },
                ],
            }
            if self.response_format:
                payload["response_format"] = {"type": "json_object"}
            return payload
        payload = {
            "model": self.model,
            "store": False,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_tokens,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": file_to_data_url(image, "image/jpeg"),
                        },
                    ],
                },
            ],
        }
        if self.response_format:
            payload["text"] = {"format": {"type": "json_object"}}
        return payload

    def analyze(
        self, image: Path, taxonomy: dict[str, list[str]], retries: int, max_tags: int
    ) -> MoodtagAnalysis:
        self.last_attempts = []
        endpoint = self.endpoint()
        if not endpoint.api_key:
            raise CoreError("Missing API key. Run `moodtag config model`.")
        if not endpoint.model:
            raise CoreError("Missing model. Run `moodtag config model`.")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                data = http_request(
                    "POST",
                    endpoint.url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {endpoint.api_key}",
                    },
                    json_body=self.build_payload(image, taxonomy),
                    timeout=180,
                    secret=endpoint.api_key,
                )
                result = parse_analysis_response(data, taxonomy, max_tags=max_tags)
            except ProviderHTTPError as exc:
                last_error = exc
                self._record_attempt(
                    endpoint, ok=False, error=exc, elapsed_ms=elapsed_ms_since(started)
                )
                if exc.status in {401, 403}:
                    raise ProviderAuthenticationError(endpoint, exc) from exc
                if exc.status not in {429} and exc.status < 500:
                    raise
            except ProviderNetworkError as exc:
                last_error = exc
                self._record_attempt(
                    endpoint, ok=False, error=exc, elapsed_ms=elapsed_ms_since(started)
                )
            except CoreError as exc:
                self._record_attempt(
                    endpoint, ok=False, error=exc, elapsed_ms=elapsed_ms_since(started)
                )
                raise
            else:
                self._record_attempt(
                    endpoint, ok=True, elapsed_ms=elapsed_ms_since(started)
                )
                self.last_endpoint_protocol = endpoint.protocol
                self.last_endpoint_base_url = endpoint.base_url
                self.last_endpoint_model = endpoint.model
                return result
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        raise CoreError(
            f"Model request failed: {redact(str(last_error), endpoint.api_key)}"
        )

    def _record_attempt(
        self,
        endpoint: ProviderEndpoint,
        *,
        ok: bool,
        elapsed_ms: int = 0,
        error: Exception | None = None,
    ) -> None:
        status = error.status if isinstance(error, ProviderHTTPError) else None
        self.last_attempts.append(
            ProviderAttempt(
                protocol=endpoint.protocol,
                base_url=endpoint.base_url,
                model=endpoint.model,
                ok=ok,
                elapsed_ms=elapsed_ms,
                status=status,
                error=redact(str(error), endpoint.api_key)[:500] if error else "",
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
