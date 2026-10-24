"""Single-endpoint OpenAI-compatible protocol adapters for moodtag."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    ANNOTATION_FIELDS,
    COMMERCIAL_CONFIDENCE_VALUES,
    COMMERCIAL_LIST_FIELDS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    SUPPORTED_PROTOCOLS,
    CoreError,
    MoodtagAnalysis,
)
from .prompts import read_system_prompt, render_user_prompt, resolve_profile
from .response import parse_analysis_response, parse_json_content

DEFAULT_USER_AGENT = "moodtag/0.1"


def redact(text: str, secret: str | None = None) -> str:
    value = str(text)
    if secret:
        value = value.replace(secret, "REDACTED")
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", value)


def url_join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


@dataclass(frozen=True)
class ProviderEndpoint:
    protocol: str
    base_url: str
    api_key: str | None
    model: str

    @property
    def url(self) -> str:
        return protocol_url(self.base_url, self.protocol)


@dataclass(frozen=True)
class ProviderAttempt:
    protocol: str
    base_url: str
    model: str
    ok: bool
    elapsed_ms: int
    status: int | None = None
    error: str = ""


class ProviderHTTPError(CoreError):
    def __init__(
        self, status: int, url: str, body: str, *, secret: str | None = None
    ) -> None:
        self.status = status
        self.url = url
        self.body = redact(body, secret)
        self.error_code, self.error_message = parse_provider_error(self.body)
        super().__init__(f"HTTP {status} from {url}: {self.body[:800]}")


class ProviderAuthenticationError(ProviderHTTPError):
    """The configured credential was rejected by the endpoint."""

    def __init__(self, endpoint: ProviderEndpoint, error: ProviderHTTPError) -> None:
        super().__init__(error.status, error.url, error.body, secret=endpoint.api_key)
        self.endpoint = endpoint
        host = urllib.parse.urlsplit(endpoint.base_url).netloc or endpoint.base_url
        self.args = (
            f"Model authentication failed for {endpoint.protocol} endpoint ({host}) "
            f"using configured API key (HTTP {error.status}). Update `moodtag config model`.",
        )


class ProviderNetworkError(CoreError):
    def __init__(self, url: str, reason: Any, *, secret: str | None = None) -> None:
        self.url = url
        self.reason = redact(reason, secret)
        super().__init__(f"Cannot reach {url}: {self.reason}")


def parse_provider_error(body: str) -> tuple[str, str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "", body
    if not isinstance(data, dict):
        return "", body
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or error.get("type") or ""), str(
            error.get("message") or ""
        )
    return str(data.get("code") or data.get("Code") or ""), str(
        data.get("message") or data.get("Message") or data.get("error") or ""
    )


def validate_protocol(protocol: str) -> str:
    value = str(protocol or "").strip().lower()
    if value not in SUPPORTED_PROTOCOLS:
        allowed = ", ".join(SUPPORTED_PROTOCOLS)
        raise CoreError(
            f"Unsupported model protocol: {value or '-'} (expected {allowed})"
        )
    return value


def normalize_base_url(base_url: str, protocol: str) -> str:
    protocol = validate_protocol(protocol)
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise CoreError("Missing model base URL. Run `moodtag config model`.")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise CoreError("Model base URL must be an absolute http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise CoreError(
            "Model base URL must not contain credentials, query, or fragment"
        )
    path = parts.path.rstrip("/")
    expected = "/chat/completions" if protocol == "chat" else "/responses"
    other = "/responses" if protocol == "chat" else "/chat/completions"
    if path.endswith(other):
        raise CoreError(
            f"Model base URL uses endpoint for protocol {other.lstrip('/')}"
        )
    if path.endswith(expected):
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def protocol_url(base_url: str, protocol: str) -> str:
    protocol = validate_protocol(protocol)
    normalized = normalize_base_url(base_url, protocol)
    parts = urllib.parse.urlsplit(normalized)
    path = parts.path.rstrip("/")
    expected = "/chat/completions" if protocol == "chat" else "/responses"
    if path.endswith(expected):
        return normalized
    if path in {"", "/"}:
        path = "/v1"
    elif path.endswith("/v1"):
        pass
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path + expected, "", "")
    )


def chat_completions_url(base_url: str) -> str:
    return protocol_url(base_url, "chat")


def responses_url(base_url: str) -> str:
    return protocol_url(base_url, "responses")


def models_url(base_url: str) -> str:
    normalized = normalize_base_url(base_url, "chat")
    parts = urllib.parse.urlsplit(normalized)
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    if path in {"", "/"}:
        path = "/v1"
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path + "/models", "", "")
    )


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    timeout: int = 60,
    secret: str | None = None,
) -> Any:
    request_headers = dict(headers or {})
    request_headers.setdefault(
        "User-Agent", os.environ.get("MOODTAG_USER_AGENT", DEFAULT_USER_AGENT)
    )
    body = None
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise ProviderHTTPError(exc.code, url, detail, secret=secret) from exc
    except urllib.error.URLError as exc:
        raise ProviderNetworkError(url, exc.reason, secret=secret) from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


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


def moodtag_json_schema(profile: str = "editorial") -> dict[str, Any]:
    """Return Ollama's structured-output schema for the current analysis contract."""
    properties: dict[str, Any] = {
        "brief": {"type": "string"},
        "elements": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "use": {"type": "string"},
        "key": {"type": "string"},
        "camera": {"type": "string"},
        "light_color": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "use_intents": {"type": "array", "items": {"type": "string"}},
    }
    required = [*ANNOTATION_FIELDS, "tags", "use_intents"]
    if profile == "editorial":
        properties.update(
            {
                field: {"type": "array", "items": {"type": "string"}}
                for field in COMMERCIAL_LIST_FIELDS
            }
        )
        properties["commercial_format_confidence"] = {
            "type": "string",
            "enum": list(COMMERCIAL_CONFIDENCE_VALUES),
        }
        required.extend([*COMMERCIAL_LIST_FIELDS, "commercial_format_confidence"])
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate the emitted contract subset without adding a runtime dependency."""
    expected = schema.get("type")
    valid = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
    }
    if expected in valid and not valid[expected](value):
        raise CoreError(
            f"Ollama schema validation failed at {path}: expected {expected}"
        )
    if "enum" in schema and value not in schema["enum"]:
        raise CoreError(f"Ollama schema validation failed at {path}: invalid value")
    if expected == "object":
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise CoreError(
                f"Ollama schema validation failed at {path}: missing required fields"
            )
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise CoreError(
                f"Ollama schema validation failed at {path}: unexpected fields"
            )
        for key, child in value.items():
            if key in properties:
                validate_json_schema(child, properties[key], f"{path}.{key}")
    if expected == "array":
        if len(value) < schema.get("minItems", 0):
            raise CoreError(f"Ollama schema validation failed at {path}: too few items")
        for index, child in enumerate(value):
            validate_json_schema(child, schema.get("items", {}), f"{path}[{index}]")


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
        self, image: Path, taxonomy: dict[str, list[str]]
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": read_system_prompt(profile=self.profile)},
                {
                    "role": "user",
                    "content": render_user_prompt(taxonomy, profile=self.profile),
                    "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
                },
            ],
            "format": moodtag_json_schema(self.profile),
            "stream": False,
            "options": self.options,
            **({"think": self.think} if self.think is not None else {}),
        }

    def analyze(
        self, image: Path, taxonomy: dict[str, list[str]], retries: int, max_tags: int
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
                data = self._request("/api/chat", self.build_payload(image, taxonomy))
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


def elapsed_ms_since(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def file_to_data_url(path: Path, mimetype: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"
