"""Native local Ollama vision client and structured-output validation."""

from __future__ import annotations

import base64
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from .common import (
    CoreError,
    ProviderAttempt,
    ProviderHTTPError,
    ProviderNetworkError,
    elapsed_ms_since,
    http_request,
    redact,
    url_join,
)
from .contract import (
    MoodtagAnalysis,
)
from .prompts import read_system_prompt, render_item_context, render_user_prompt
from .response import parse_analysis_response, parse_json_content
from .schema import moodtag_json_schema, validate_json_schema

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


class OllamaVisionClient:
    """Native, same-provider Ollama vision client; never falls back to cloud."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str,
        profile: str = "editorial",
        preset: str = "qwen-instruct",
        options: dict[str, Any] | None = None,
        timeout: int = 180,
        local_only: bool = True,
        output_language: str = "zh",
    ) -> None:
        parts = urllib.parse.urlsplit(base_url.rstrip("/"))
        if (
            parts.scheme != "http"
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise CoreError("Ollama requires an http endpoint without credentials")
        if local_only and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise CoreError("Local-only Ollama endpoint must use loopback")
        if preset not in OLLAMA_PRESETS:
            raise CoreError(f"Unknown Ollama preset: {preset}")
        self.base_url = base_url.rstrip("/")
        self.model = str(model).strip()
        if not self.model:
            raise CoreError("Missing Ollama model")
        self.profile = profile
        self.output_language = output_language
        self.preset = preset
        self.options = dict(OLLAMA_PRESETS[preset])
        self.options.pop("think", None)
        self.options.update(options or {})
        self.think = OLLAMA_PRESETS[preset].get("think")
        self.timeout = timeout
        self.local_only = local_only
        self.last_endpoint_protocol = "ollama"
        self.last_endpoint_base_url = self.base_url
        self.last_endpoint_model = self.model
        self.last_attempts: list[ProviderAttempt] = []
        self.runtime: dict[str, Any] = {}
        self._preflight_done = False

    def preflight(self, *, startup_timeout: float = 15.0) -> str:
        """Reuse Ollama, or make one bounded attempt to open Ollama.app on macOS."""
        if self._preflight_done:
            return str(self.runtime.get("version", "unknown"))
        try:
            version = self.version()
            self.runtime["version"] = version
            self._preflight_done = True
            return version
        except (ProviderHTTPError, ProviderNetworkError, CoreError) as first_error:
            if sys.platform != "darwin":
                raise CoreError(
                    "Ollama is unavailable; start the local Ollama service"
                ) from first_error
        try:
            subprocess.run(
                ["open", "-j", "-a", "Ollama"],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CoreError(
                "Cannot start Ollama.app; install or open Ollama manually"
            ) from exc
        deadline = time.monotonic() + max(0, startup_timeout)
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                version = self.version()
                self.runtime["version"] = version
                self._preflight_done = True
                return version
            except (ProviderHTTPError, ProviderNetworkError, CoreError) as exc:
                last_error = exc
                time.sleep(0.5)
        raise CoreError(
            "Ollama did not become ready; open Ollama and retry"
        ) from last_error

    def _request(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return http_request(
            "POST" if body is not None else "GET",
            url_join(self.base_url, path),
            json_body=body,
            timeout=self.timeout,
        )

    def version(self) -> str:
        data = self._request("/api/version")
        return (
            str(data.get("version", "unknown")) if isinstance(data, dict) else "unknown"
        )

    def models(self) -> list[dict[str, Any]]:
        data = self._request("/api/tags")
        return list(data.get("models", [])) if isinstance(data, dict) else []

    def inspect_model(self, model: str | None = None) -> dict[str, Any]:
        data = self._request(
            "/api/show", {"model": model or self.model, "verbose": True}
        )
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _check_locality(metadata: dict[str, Any]) -> None:
        def has_remote_signal(value: Any) -> bool:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.lower() in {"remote_model", "remote_host"} and child:
                        return True
                    if key.lower() == "capabilities" and isinstance(child, list):
                        if any(
                            str(item).lower() in {"remote", "cloud"} for item in child
                        ):
                            return True
                    if has_remote_signal(child):
                        return True
            elif isinstance(value, list):
                return any(has_remote_signal(child) for child in value)
            return False

        if has_remote_signal(metadata):
            raise CoreError(
                "Ollama model locality is remote or unconfirmed; local-only analysis refused"
            )

    def build_payload(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        *,
        original_title: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": read_system_prompt(profile=self.profile)},
                {
                    "role": "user",
                    "content": render_user_prompt(
                        taxonomy,
                        profile=self.profile,
                        output_language=self.output_language,
                    )
                    + render_item_context(original_title, source_url),
                    "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
                },
            ],
            "format": moodtag_json_schema(self.profile),
            "stream": False,
            "options": self.options,
            **({"think": self.think} if self.think is not None else {}),
        }

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
        self.preflight()
        if self.local_only:
            model_meta = next(
                (
                    item
                    for item in self.models()
                    if item.get("name") == self.model or item.get("model") == self.model
                ),
                None,
            )
            if not model_meta:
                raise CoreError(
                    f"Ollama model is not installed: {self.model}; install it explicitly first"
                )
            show = self.inspect_model()
            capabilities = show.get("capabilities", model_meta.get("capabilities", []))
            if "vision" not in capabilities:
                raise CoreError(
                    "Selected Ollama model does not advertise vision capability"
                )
            self._check_locality({"tags": model_meta, "show": show})
            model_info = show.get("model_info", {})
            architecture = (
                str(model_info.get("general.architecture", ""))
                if isinstance(model_info, dict)
                else ""
            )
            context_capacity = (
                model_info.get(f"{architecture}.context_length")
                if architecture and isinstance(model_info, dict)
                else None
            )
            self.runtime.update(
                {
                    "version": self.runtime.get("version", "unknown"),
                    "digest": model_meta.get("digest", "unknown"),
                    "runner": (
                        show.get("details", {}).get("runner")
                        or model_meta.get("details", {}).get("runner")
                        or "unknown"
                    ),
                    "capabilities": capabilities,
                    "model_context_capacity": context_capacity,
                    "thinking_supported": "thinking" in capabilities,
                    "model_parameters": show.get("parameters", ""),
                }
            )
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(min(max(0, retries), 2) + 1):
            try:
                data = self._request(
                    "/api/chat",
                    self.build_payload(
                        image,
                        taxonomy,
                        original_title=original_title,
                        source_url=source_url,
                    ),
                )
                if not isinstance(data, dict) or data.get("done") is not True:
                    raise CoreError("Ollama response did not finish normally")
                reason = str(data.get("done_reason", "stop"))
                if reason not in {"stop", ""}:
                    raise CoreError(f"Ollama response ended prematurely ({reason})")
                self._check_locality(data)
                message = data.get("message")
                content = message.get("content") if isinstance(message, dict) else ""
                if not isinstance(content, str) or not content.strip():
                    raise CoreError("Ollama response has no assistant content")
                parsed = parse_json_content(content)
                validate_json_schema(parsed, moodtag_json_schema(self.profile))
                raw_tags = parsed.get("tags", [])
                if isinstance(raw_tags, list):
                    normalized_tags = [
                        str(tag).strip().casefold()
                        for tag in raw_tags
                        if str(tag).strip()
                    ]
                    self.runtime["raw_duplicate_tag_count"] = len(
                        normalized_tags
                    ) - len(set(normalized_tags))
                result = parse_analysis_response(
                    {"choices": [{"message": {"content": content}}]},
                    taxonomy,
                    max_tags=max_tags,
                )
                self.runtime.update(
                    {
                        k: data.get(k)
                        for k in (
                            "load_duration",
                            "prompt_eval_duration",
                            "eval_duration",
                            "prompt_eval_count",
                            "prompt_eval_cached_count",
                            "eval_count",
                        )
                    }
                )
                self.runtime["done_reason"] = data.get("done_reason")
                thinking = message.get("thinking")
                self.runtime["thinking_enabled"] = self.think is True
                self.runtime["thinking_output_present"] = (
                    bool(thinking.strip()) if isinstance(thinking, str) else False
                )
                self.runtime["thinking_chars"] = (
                    len(thinking) if isinstance(thinking, str) else 0
                )
                self.runtime["content_chars"] = len(content)
                eval_count = data.get("eval_count")
                eval_duration = data.get("eval_duration")
                if (
                    isinstance(eval_count, int | float)
                    and isinstance(eval_duration, int | float)
                    and eval_duration > 0
                ):
                    self.runtime["eval_tokens_per_second"] = eval_count / (
                        eval_duration / 1_000_000_000
                    )
                self.runtime["end_to_end_ms"] = elapsed_ms_since(started)
                stage_ms = sum(
                    max(0, int(data.get(key) or 0)) // 1_000_000
                    for key in (
                        "load_duration",
                        "prompt_eval_duration",
                        "eval_duration",
                    )
                )
                self.runtime["queue_wait_ms_estimated"] = max(
                    0, self.runtime["end_to_end_ms"] - stage_ms
                )
                self.last_attempts = [
                    ProviderAttempt(
                        "ollama",
                        self.base_url,
                        self.model,
                        True,
                        self.runtime["end_to_end_ms"],
                    )
                ]
                return result
            except (CoreError, ProviderHTTPError, ProviderNetworkError) as exc:
                last_error = exc
                if attempt >= min(max(0, retries), 2):
                    break
                time.sleep(0.5 * (attempt + 1))
        self.last_attempts = [
            ProviderAttempt(
                "ollama",
                self.base_url,
                self.model,
                False,
                elapsed_ms_since(started),
                error=redact(str(last_error))[:500],
            )
        ]
        raise CoreError(f"Ollama analysis failed: {last_error}") from last_error
