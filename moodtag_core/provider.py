"""OpenAI-compatible chat completion provider for moodtag."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_PROVIDER_COOLDOWN_SECONDS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    CoreError,
    MoodtagAnalysis,
)
from .prompts import read_system_prompt, render_user_prompt
from .response import parse_analysis_response

DEFAULT_USER_AGENT = "moodtag/0.1"
PRIMARY_PROVIDER_NAME = "primary"
FALLBACK_PROVIDER_NAME = "fallback"
FALLBACK_STATUS_CODES = {429}
NON_FALLBACK_STATUS_CODES = {400, 401, 403, 404}
FALLBACK_ERROR_PATTERNS = (
    "arrearage",
    "allocationquota",
    "commoditynotpurchased",
    "freetier",
    "free allocated quota exceeded",
    "insufficient_quota",
    "postpaidbilloverdue",
    "prepaidbilloverdue",
    "quota",
    "rate limit",
    "rate_limit",
    "throttling",
)


def redact(text: str) -> str:
    import re

    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", str(text))


def url_join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


@dataclass(frozen=True)
class ProviderEndpoint:
    name: str
    base_url: str
    api_key: str | None
    model: str


@dataclass(frozen=True)
class ProviderAttempt:
    name: str
    base_url: str
    model: str
    ok: bool
    elapsed_ms: int
    status: int | None = None
    error: str = ""


class ProviderHTTPError(CoreError):
    def __init__(self, status: int, url: str, body: str) -> None:
        self.status = status
        self.url = url
        self.body = body
        self.error_code, self.error_message = parse_provider_error(body)
        detail = body[:800]
        super().__init__(f"HTTP {status} from {url}: {redact(detail)}")


class ProviderNetworkError(CoreError):
    def __init__(self, url: str, reason: Any) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Cannot reach {url}: {reason}")


def parse_provider_error(body: str) -> tuple[str, str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "", body
    if not isinstance(data, dict):
        return "", body
    error = data.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("type") or ""
        message = error.get("message") or ""
        return str(code), str(message)
    code = data.get("code") or data.get("Code") or ""
    message = data.get("message") or data.get("Message") or data.get("error") or ""
    return str(code), str(message)


def provider_cache_path() -> Path:
    override = os.environ.get("MOODTAG_PROVIDER_STATE", "").strip()
    if override:
        return Path(override).expanduser()
    xdg_home = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".cache"
    return root / "moodtag" / "provider-state.json"


def load_provider_state(path: Path | None = None) -> dict[str, Any]:
    path = path or provider_cache_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_provider_state(state: dict[str, Any], path: Path | None = None) -> None:
    path = path or provider_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def provider_in_cooldown(name: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    entry = load_provider_state().get(name)
    if not isinstance(entry, dict):
        return False
    try:
        disabled_until = float(entry.get("disabled_until", 0))
    except (TypeError, ValueError):
        return False
    return disabled_until > now


def record_provider_cooldown(
    name: str,
    error: Exception,
    *,
    cooldown_seconds: int = DEFAULT_PROVIDER_COOLDOWN_SECONDS,
    now: float | None = None,
) -> None:
    if cooldown_seconds <= 0:
        return
    now = time.time() if now is None else now
    state = load_provider_state()
    state[name] = {
        "disabled_until": now + cooldown_seconds,
        "reason": redact(str(error))[:500],
    }
    save_provider_state(state)


def is_fallback_error(error: Exception) -> bool:
    if isinstance(error, ProviderNetworkError):
        return True
    if isinstance(error, ProviderHTTPError):
        if error.status >= 500 or error.status in FALLBACK_STATUS_CODES:
            return True
        if error.status in NON_FALLBACK_STATUS_CODES:
            haystack = " ".join(
                [error.error_code, error.error_message, error.body]
            ).lower()
            return any(pattern in haystack for pattern in FALLBACK_ERROR_PATTERNS)
    return False


def chat_completions_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise CoreError("Missing --base-url value")
    parts = urllib.parse.urlsplit(base_url)
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return base_url
    if path.endswith("/v1"):
        return url_join(base_url, "/chat/completions")
    if path in {"", "/"}:
        v1_base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/v1", "", ""))
        return url_join(v1_base, "/chat/completions")
    return url_join(base_url, "/chat/completions")


def models_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise CoreError("Missing --base-url value")
    parts = urllib.parse.urlsplit(base_url)
    path = parts.path.rstrip("/")
    if path.endswith("/models"):
        return base_url
    if path.endswith("/v1"):
        return url_join(base_url, "/models")
    if path in {"", "/"}:
        v1_base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/v1", "", ""))
        return url_join(v1_base, "/models")
    return url_join(base_url, "/models")


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    timeout: int = 60,
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
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderHTTPError(exc.code, url, detail) from exc
    except urllib.error.URLError as exc:
        raise ProviderNetworkError(url, exc.reason) from exc
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
        base_url: str,
        fallback_base_url: str = "",
        model: str,
        api_key: str | None,
        fallback_model: str | None = None,
        fallback_api_key: str | None = None,
        cooldown_seconds: int = DEFAULT_PROVIDER_COOLDOWN_SECONDS,
        response_format: bool = not DEFAULT_NO_RESPONSE_FORMAT,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model if fallback_model is not None else model
        self.api_key = api_key
        self.fallback_api_key = (
            fallback_api_key if fallback_api_key is not None else api_key
        )
        self.cooldown_seconds = cooldown_seconds
        self.response_format = response_format
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.last_provider_name = ""
        self.last_provider_base_url = ""
        self.last_provider_model = ""
        self.last_provider_attempts: list[ProviderAttempt] = []

    def base_urls(self) -> list[str]:
        return [
            endpoint.base_url for endpoint in self.endpoints(include_cooldown=False)
        ]

    def endpoints(self, *, include_cooldown: bool = True) -> list[ProviderEndpoint]:
        endpoints: list[ProviderEndpoint] = []
        seen: set[tuple[str, str | None, str]] = set()
        for name, raw_url, api_key, model in (
            (PRIMARY_PROVIDER_NAME, self.base_url, self.api_key, self.model),
            (
                FALLBACK_PROVIDER_NAME,
                self.fallback_base_url,
                self.fallback_api_key,
                self.fallback_model,
            ),
        ):
            url = raw_url.strip().rstrip("/")
            key = (url, api_key, model)
            if not url or key in seen:
                continue
            if include_cooldown and name == PRIMARY_PROVIDER_NAME:
                if provider_in_cooldown(PRIMARY_PROVIDER_NAME):
                    continue
            endpoints.append(
                ProviderEndpoint(
                    name=name,
                    base_url=url,
                    api_key=api_key,
                    model=model,
                )
            )
            seen.add(key)
        return endpoints

    def build_payload(
        self, image: Path, taxonomy: dict[str, list[str]], model: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": read_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": file_to_data_url(image, "image/jpeg")},
                        },
                        {"type": "text", "text": render_user_prompt(taxonomy)},
                    ],
                },
            ],
        }
        if self.response_format:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def analyze(
        self, image: Path, taxonomy: dict[str, list[str]], retries: int, max_tags: int
    ) -> MoodtagAnalysis:
        self.last_provider_name = ""
        self.last_provider_base_url = ""
        self.last_provider_model = ""
        self.last_provider_attempts = []
        endpoints = self.endpoints()
        if not endpoints:
            raise CoreError("Missing --base-url value")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            response_error = False
            for endpoint in endpoints:
                if not endpoint.api_key:
                    last_error = CoreError(provider_missing_key_message(endpoint.name))
                    self._record_attempt(endpoint, ok=False, error=last_error)
                    if (
                        endpoint.name == PRIMARY_PROVIDER_NAME
                        and self.fallback_base_url
                    ):
                        continue
                    raise last_error
                try:
                    started = time.monotonic()
                    payload = self.build_payload(image, taxonomy, model=endpoint.model)
                    data = http_request(
                        "POST",
                        chat_completions_url(endpoint.base_url),
                        headers={
                            "Accept": "application/json",
                            "Authorization": f"Bearer {endpoint.api_key}",
                        },
                        json_body=payload,
                        timeout=180,
                    )
                except Exception as exc:  # noqa: BLE001 - retry boundary
                    last_error = exc
                    self._record_attempt(
                        endpoint,
                        ok=False,
                        error=exc,
                        elapsed_ms=elapsed_ms_since(started),
                    )
                    if endpoint.name == PRIMARY_PROVIDER_NAME and is_fallback_error(
                        exc
                    ):
                        if self.fallback_base_url:
                            record_provider_cooldown(
                                PRIMARY_PROVIDER_NAME,
                                exc,
                                cooldown_seconds=self.cooldown_seconds,
                            )
                            continue
                    if isinstance(exc, ProviderHTTPError) and not is_fallback_error(
                        exc
                    ):
                        raise exc
                    continue
                try:
                    result = parse_analysis_response(data, taxonomy, max_tags=max_tags)
                except CoreError as exc:
                    last_error = exc
                    self._record_attempt(
                        endpoint,
                        ok=False,
                        error=exc,
                        elapsed_ms=elapsed_ms_since(started),
                    )
                    response_error = True
                    break
                self.last_provider_name = endpoint.name
                self.last_provider_base_url = endpoint.base_url
                self.last_provider_model = endpoint.model
                self._record_attempt(
                    endpoint,
                    ok=True,
                    elapsed_ms=elapsed_ms_since(started),
                )
                return result
            if response_error and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        raise CoreError(f"VL request failed: {redact(str(last_error))}")

    def _record_attempt(
        self,
        endpoint: ProviderEndpoint,
        *,
        ok: bool,
        elapsed_ms: int = 0,
        error: Exception | None = None,
    ) -> None:
        status = error.status if isinstance(error, ProviderHTTPError) else None
        self.last_provider_attempts.append(
            ProviderAttempt(
                name=endpoint.name,
                base_url=endpoint.base_url,
                model=endpoint.model,
                ok=ok,
                elapsed_ms=elapsed_ms,
                status=status,
                error=redact(str(error))[:500] if error else "",
            )
        )


def provider_missing_key_message(name: str) -> str:
    if name == PRIMARY_PROVIDER_NAME:
        return (
            "Missing primary API key. Set DASHSCOPE_API_KEY, "
            "or configure fallback with MOODTAG_API_KEY/VL_API_KEY."
        )
    return "Missing fallback API key. Set MOODTAG_API_KEY or VL_API_KEY."


def elapsed_ms_since(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def file_to_data_url(path: Path, mimetype: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"
