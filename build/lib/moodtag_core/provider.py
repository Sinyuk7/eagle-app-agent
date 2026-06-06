"""OpenAI-compatible chat completion provider for moodtag."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .contract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    CoreError,
    MoodtagAnalysis,
)
from .prompts import read_system_prompt, render_user_prompt
from .response import parse_analysis_response


DEFAULT_USER_AGENT = "moodtag/0.1"


def redact(text: str) -> str:
    import re

    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", str(text))


def url_join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


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
        v1_base = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/v1", "", "")
        )
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
        v1_base = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/v1", "", "")
        )
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
        raise CoreError(f"HTTP {exc.code} from {url}: {redact(detail[:800])}") from exc
    except urllib.error.URLError as exc:
        raise CoreError(f"Cannot reach {url}: {exc.reason}") from exc
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
        response_format: bool = not DEFAULT_NO_RESPONSE_FORMAT,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.response_format = response_format
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

    def base_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for raw_url in (self.base_url, self.fallback_base_url):
            url = raw_url.strip().rstrip("/")
            if url and url not in seen:
                urls.append(url)
                seen.add(url)
        return urls

    def build_payload(self, image: Path, taxonomy: dict[str, list[str]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
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
        if not self.api_key:
            raise CoreError("Missing API key. Set MOODTAG_API_KEY or VL_API_KEY.")
        payload = self.build_payload(image, taxonomy)
        base_urls = self.base_urls()
        if not base_urls:
            raise CoreError("Missing --base-url value")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            for base_url in base_urls:
                try:
                    data = http_request(
                        "POST",
                        chat_completions_url(base_url),
                        headers={
                            "Accept": "application/json",
                            "Authorization": f"Bearer {self.api_key}",
                        },
                        json_body=payload,
                        timeout=180,
                    )
                except Exception as exc:  # noqa: BLE001 - retry boundary
                    last_error = exc
                    continue
                return parse_analysis_response(data, taxonomy, max_tags=max_tags)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        raise CoreError(f"VL request failed: {redact(str(last_error))}")


def file_to_data_url(path: Path, mimetype: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"
