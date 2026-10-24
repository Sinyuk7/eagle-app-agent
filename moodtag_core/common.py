"""Shared provider transport, endpoint, error, and utility primitives."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import SUPPORTED_PROTOCOLS, CoreError

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


def elapsed_ms_since(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def file_to_data_url(path: Path, mimetype: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"
