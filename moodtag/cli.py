#!/usr/bin/env python3
"""Moodtag: folder-first moodboard tagging for Eagle."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import contextlib
import getpass
import importlib.metadata
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time  # noqa: F401 - tests patch module-level timing
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moodtag_core.annotation import (
    ANNOTATION_LABEL_ORDER,
    analysis_status,
    build_annotation_block,
    extract_brief,
    has_analysis_annotation,
    parse_annotation_fields,
    remove_analysis_annotation,
    replace_analysis_annotation,
)
from moodtag_core.catalog import (
    load_model_catalog,
    protocol_for_model,
)
from moodtag_core.contract import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    MIN_MAX_TOKENS,
    CoreError,
    MoodtagAnalysis,
)
from moodtag_core.envelope import normalize_usage
from moodtag_core.prompts import resolve_profile
from moodtag_core.provider import (
    OllamaVisionClient,
    ProviderAuthenticationError,
    elapsed_ms_since,
    normalize_base_url,
)
from moodtag_core.provider import (
    VisionClient as CoreVisionClient,
)
from moodtag_core.response import normalize_analysis_json, parse_analysis_response
from moodtag_core.taxonomy import load_profile_taxonomy

from .config import (
    ACTIVE_PROFILE_KEY,
    NAMED_PROFILES_KEY,
    ConfigError,
    config_path,
    load_user_config,
    public_config_view,
    save_user_config,
    update_user_config,
)
from .ui.locale import tr
from .ui.menu import MenuCancelled, MenuChoice, choose
from .ui.printer import Printer
from .ui.session import Session
from .ui.spinner import spinner

DEFAULT_EAGLE_API = "http://localhost:41595"
DEFAULT_IMAGE_EDGE = 768
DEFAULT_CONCURRENCY = 10
DEFAULT_MAX_TAGS = 15
DEFAULT_RETRIES = 2
DEFAULT_USER_AGENT = "moodtag/0.1"
DEFAULT_LOG_KEEP = 50
DEFAULT_MAX_BOARD_ITEMS = 9999
DEFAULT_PROFILE = "editorial"
TAGGING_STYLE_NAMES = {
    "editorial": "Editorial",
    "default": "General",
}
MAIN_FLOW_COMMANDS = {"status", "tag", "brief", "export-context", "reset", "config"}
SUPPORTED_ORIGINAL_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
}
EAGLE_SHAPES = (
    "square",
    "portrait",
    "panoramic-portrait",
    "landscape",
    "panoramic-landscape",
)


class MoodtagError(CoreError):
    """Expected runtime error shown without traceback."""


class SetupCancelled(MoodtagError):
    """Interactive model setup ended without changing configuration."""


def tagging_style_name(profile: str) -> str:
    return TAGGING_STYLE_NAMES.get(profile, profile)


@dataclass(frozen=True)
class RunResult:
    """Stable final result for both human and JSON command paths."""

    board: str
    total: int
    selected: int
    changed: int
    skipped: int
    failed: int
    cancelled: bool = False
    error: str = ""

    @property
    def exit_code(self) -> int:
        if self.cancelled:
            return 130
        return 1 if self.failed else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "total": self.total,
            "selected": self.selected,
            "changed": self.changed,
            "skipped": self.skipped,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "error": self.error,
            "exit_code": self.exit_code,
        }


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    path: str
    parent: str | None = None


@dataclass(frozen=True)
class BoardScopeFolder:
    board: Board
    item_count: int


@dataclass(frozen=True)
class BoardScope:
    board: Board
    folders: list[BoardScopeFolder]
    items: list[EagleItem]


@dataclass(frozen=True)
class ScopeInput:
    folder: str = ""
    selected: bool = False
    library: bool = False
    tags: tuple[str, ...] = ()
    recursive: bool = True
    max_items: int = DEFAULT_MAX_BOARD_ITEMS
    rating: int | None = None
    shape: str = ""


@dataclass(frozen=True)
class ResolvedScope:
    source: str
    items: list[EagleItem]

    @property
    def total(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class EagleItem:
    id: str
    name: str
    ext: str
    tags: list[str]
    folders: list[str]
    annotation: str
    width: int | None = None
    height: int | None = None
    size: int | None = None
    palettes: list[dict[str, Any]] = field(default_factory=list)
    rating: int | None = None


@dataclass(frozen=True)
class Preview:
    path: Path
    source_path: Path
    source_width: int
    source_height: int
    width: int
    height: int
    mimetype: str = "image/jpeg"


class TagRunLog:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    def write(self, event: str, **payload: Any) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "event": event,
            **payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(redact(json.dumps(record, ensure_ascii=False)) + "\n")
        except OSError:
            return


@dataclass(frozen=True)
class TagItemResult:
    index: int
    item: EagleItem
    tags: list[str] = field(default_factory=list)
    annotation: str = ""
    model_endpoint: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    source_strategy: str = ""
    elapsed_ms: int = 0
    error: Exception | None = None


def redact(text: str, secret: str | None = None) -> str:
    value = str(text)
    if secret:
        value = value.replace(secret, "REDACTED")
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", value)


def log_root() -> Path:
    override = os.environ.get("MOODTAG_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    xdg_home = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".cache"
    return root / "moodtag" / "runs"


def make_tag_run_log(*, keep: int = DEFAULT_LOG_KEEP) -> TagRunLog:
    root = log_root()
    keep = log_keep(default=keep)
    run_id = uuid.uuid4().hex[:12]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = root / f"moodtag-{stamp}-{run_id}.jsonl"
    try:
        root.mkdir(parents=True, exist_ok=True)
        prune_old_logs(root, keep=keep - 1)
        path.touch(exist_ok=False)
    except OSError:
        path = Path(os.devnull)
    return TagRunLog(path, run_id)


def log_keep(*, default: int = DEFAULT_LOG_KEEP) -> int:
    raw = os.environ.get("MOODTAG_LOG_KEEP", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def prune_old_logs(root: Path, *, keep: int) -> None:
    if keep < 0:
        keep = 0
    try:
        logs = [
            path
            for path in root.glob("moodtag-*.jsonl")
            if path.is_file() and path.name.startswith("moodtag-")
        ]
    except OSError:
        return
    logs.sort(key=lambda path: (safe_mtime(path), path.name), reverse=True)
    for path in logs[keep:]:
        try:
            path.unlink()
        except OSError:
            continue


def safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def url_join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def load_env_defaults() -> None:
    inherited_api_key = bool(os.environ.get("MOODTAG_API_KEY", "").strip())
    user_env = env_file_path()
    if user_env != Path.cwd() / ".env":
        load_env_file(user_env)
    load_env_file(Path.cwd() / ".env")
    if os.environ.get("MOODTAG_API_KEY", "").strip():
        os.environ["_MOODTAG_API_KEY_SOURCE"] = (
            "environment override" if inherited_api_key else "saved credential"
        )


def env_file_path() -> Path:
    return config_path().with_name(".env")


def load_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise MoodtagError(f"Cannot read env file {path}: {exc}") from exc

    inherited_keys = set(os.environ)
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise MoodtagError(f"Invalid env line in {path}:{line_number}")
        if key in inherited_keys:
            continue
        os.environ[key] = parse_env_value(raw_value)


def parse_env_value(raw_value: str) -> str:
    try:
        parts = shlex.split(raw_value, comments=True, posix=True)
    except ValueError as exc:
        raise MoodtagError(f"Invalid quoted env value: {exc}") from exc
    return " ".join(parts)


def quote_env_value(value: str) -> str:
    return shlex.quote(value)


def save_env_values(values: dict[str, str], path: Path | None = None) -> Path:
    path = path or env_file_path()
    clean = {
        key: str(value).strip() for key, value in values.items() if str(value).strip()
    }
    if not clean:
        raise MoodtagError("Pass at least one env value to set")

    try:
        existing_lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        existing_lines = []
    except OSError as exc:
        raise MoodtagError(f"Cannot write env file {path}: {exc}") from exc

    rendered: list[str] = []
    replaced: set[str] = set()
    for raw_line in existing_lines:
        stripped = raw_line.strip()
        candidate = (
            stripped[len("export ") :].strip()
            if stripped.startswith("export ")
            else stripped
        )
        key, separator, _value = candidate.partition("=")
        key = key.strip()
        if separator and key in clean:
            rendered.append(f"{key}={quote_env_value(clean[key])}")
            replaced.add(key)
        else:
            rendered.append(raw_line)

    for key, value in clean.items():
        if key in replaced:
            continue
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append(f"{key}={quote_env_value(value)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    return path


def remove_env_value(key: str, path: Path | None = None) -> Path:
    path = path or env_file_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return path
    kept = [
        line
        for line in lines
        if not re.match(rf"\s*(?:export\s+)?{re.escape(key)}\s*=", line)
    ]
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    return path


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise MoodtagError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise MoodtagError(f"{name} must be at least {minimum}")
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise MoodtagError(f"{name} must be a number") from exc
    if minimum is not None and value < minimum:
        raise MoodtagError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise MoodtagError(f"{name} must be at most {maximum}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise MoodtagError(f"{name} must be true or false")


def prompt_yes_no(
    prompt: str, *, default: bool = False, printer: Printer | None = None
) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    printer = printer or Printer()
    while True:
        try:
            printer.emit(f"{prompt} {suffix} · {tr('q Quit', 'q 退出')}")
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise MoodtagError("Setup cancelled.") from exc
        if answer in {"q", "quit"}:
            return False
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        printer.emit(tr("Enter y or n.", "请输入 y 或 n。"), state="warning")


def public_attr(name: str) -> Any:
    package = sys.modules.get("moodtag")
    if package is not None and hasattr(package, name):
        return getattr(package, name)
    return globals()[name]


def config_value(
    config: dict[str, str], env_name: str, config_key: str, default: str
) -> str:
    raw = os.environ.get(env_name)
    if raw is not None and raw.strip():
        return raw
    return config.get(config_key) or default


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
        raise MoodtagError(
            f"HTTP {exc.code} from {url}: {redact(detail[:800])}"
        ) from exc
    except urllib.error.URLError as exc:
        raise MoodtagError(f"Cannot reach {url}: {exc.reason}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class EagleClient:
    def __init__(self, base_url: str = DEFAULT_EAGLE_API) -> None:
        self.base_url = base_url.rstrip("/")

    def app_info(self) -> dict[str, Any]:
        data = http_request(
            "GET", url_join(self.base_url, "/api/application/info"), timeout=5
        )
        self._expect_success(data, "app info")
        return data["data"]

    def library_info(self) -> dict[str, Any]:
        data = http_request(
            "GET", url_join(self.base_url, "/api/library/info"), timeout=10
        )
        self._expect_success(data, "library info")
        return data["data"]

    def boards(self) -> list[Board]:
        data = http_request(
            "GET", url_join(self.base_url, "/api/folder/list"), timeout=10
        )
        self._expect_success(data, "folder list")
        folders = data.get("data", [])
        if not isinstance(folders, list):
            folders = []
        library_name = ""
        try:
            lib = self.library_info()
            library_name = str(lib.get("library", {}).get("name") or "").strip()
        except Exception:
            pass
        boards: list[Board] = []

        def visit(
            items: list[dict[str, Any]], prefix: str = "", parent_id: str | None = None
        ) -> None:
            for item in items:
                folder_id = str(item.get("id", "")).strip()
                name = str(item.get("name", "")).strip()
                if not folder_id or not name:
                    continue
                path = f"{prefix}/{name}" if prefix else name
                parent = str(item.get("parent") or parent_id or "").strip() or None
                boards.append(Board(id=folder_id, name=name, path=path, parent=parent))
                children = item.get("children") or []
                if isinstance(children, list):
                    visit(children, path, folder_id)

        visit(folders)
        if library_name:
            boards.extend(
                Board(
                    id=b.id,
                    name=b.name,
                    path=f"{library_name}/{b.path}",
                    parent=b.parent,
                )
                for b in list(boards)
            )
        return boards

    def list_items(
        self,
        folder_id: str,
        *,
        limit: int = 1000,
        selected: bool = False,
        rating: int | None = None,
        shape: str = "",
        required_tags: tuple[str, ...] = (),
        max_matches: int = -1,
    ) -> list[EagleItem]:
        """Read every page; Eagle may cap a requested limit at 1000."""
        if rating is not None and not 0 <= rating <= 5:
            raise MoodtagError("--rating must be between 0 and 5")
        if shape and shape not in EAGLE_SHAPES:
            raise MoodtagError(f"Unsupported Eagle Shape: {shape}")
        items: list[EagleItem] = []
        offset = 0
        while True:
            data = http_request(
                "POST",
                url_join(self.base_url, "/api/v2/item/get"),
                json_body={
                    **({"folders": [folder_id]} if folder_id else {}),
                    **({"isSelected": True} if selected else {}),
                    **({"rating": rating} if rating is not None else {}),
                    **({"shape": shape} if shape else {}),
                    "limit": limit,
                    "offset": offset,
                },
                timeout=30,
            )
            if not isinstance(data, dict) or data.get("status") != "success":
                if selected or rating is not None or shape:
                    raise MoodtagError(
                        "Eagle API could not apply the requested scope filter"
                    )
                break
            payload = data.get("data") if isinstance(data.get("data"), dict) else {}
            raw_items = payload.get("data", [])
            if not isinstance(raw_items, list):
                raise MoodtagError("Eagle item list returned invalid page data")
            page_size = len(raw_items)
            page = [parse_item(raw) for raw in raw_items]
            if required_tags:
                wanted = tuple(tag.casefold() for tag in required_tags)
                page = [
                    item
                    for item in page
                    if all(
                        any(existing.casefold() == tag for existing in item.tags)
                        for tag in wanted
                    )
                ]
            items.extend(page)
            if max_matches >= 0 and len(items) > max_matches:
                raise MoodtagError(
                    f"Entire library scope exceeds --max-board-items {max_matches}. "
                    "Add filters or increase --max-board-items if this is intentional."
                )
            total = payload.get("total")
            page_limit = int(payload.get("limit") or limit)
            page_offset = int(payload.get("offset") or offset)
            if total is None:
                if page_size < page_limit:
                    return items
            elif page_offset + page_size >= int(total):
                return items
            if page_size == 0:
                raise MoodtagError("Eagle item list pagination stopped before total")
            offset = page_offset + page_size

        if selected or rating is not None or shape:
            raise MoodtagError("Eagle API could not return the complete filtered scope")
        # Fallback to the documented v1 list endpoint, which may also paginate.
        offset = 0
        while True:
            query = urllib.parse.urlencode(
                {"folders": folder_id, "limit": limit, "offset": offset}
            )
            data = http_request(
                "GET", url_join(self.base_url, f"/api/item/list?{query}"), timeout=30
            )
            self._expect_success(data, "item list")
            raw_items = data.get("data", [])
            if not isinstance(raw_items, list):
                raise MoodtagError("Eagle item list returned invalid page data")
            page_size = len(raw_items)
            page = [parse_item(raw) for raw in raw_items]
            if required_tags:
                wanted = tuple(tag.casefold() for tag in required_tags)
                page = [
                    item
                    for item in page
                    if all(
                        any(existing.casefold() == tag for existing in item.tags)
                        for tag in wanted
                    )
                ]
            items.extend(page)
            if max_matches >= 0 and len(items) > max_matches:
                raise MoodtagError(
                    f"Entire library scope exceeds --max-board-items {max_matches}. "
                    "Add filters or increase --max-board-items if this is intentional."
                )
            total = data.get("total")
            if total is None:
                return items
            if offset + page_size >= int(total):
                return items
            if page_size == 0:
                raise MoodtagError("Eagle item list pagination stopped before total")
            offset += page_size

    def count_items(
        self,
        folder_id: str = "",
        *,
        selected: bool = False,
        rating: int | None = None,
        shape: str = "",
    ) -> int | None:
        """Return Eagle's server-side item count without fetching all metadata."""
        data = http_request(
            "POST",
            url_join(self.base_url, "/api/v2/item/get"),
            json_body={
                **({"folders": [folder_id]} if folder_id else {}),
                **({"isSelected": True} if selected else {}),
                **({"rating": rating} if rating is not None else {}),
                **({"shape": shape} if shape else {}),
                "limit": 1,
                "offset": 0,
            },
            timeout=30,
        )
        if not isinstance(data, dict) or data.get("status") != "success":
            return None
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        total = payload.get("total")
        try:
            return int(total) if total is not None else None
        except (TypeError, ValueError):
            return None

    def thumbnail_path(self, item_id: str) -> Path:
        query = urllib.parse.urlencode({"id": item_id})
        data = http_request(
            "GET", url_join(self.base_url, f"/api/item/thumbnail?{query}"), timeout=10
        )
        self._expect_success(data, "item thumbnail")
        raw = str(data.get("data", ""))
        if raw.startswith("file://"):
            raw = raw[len("file://") :]
        path = Path(urllib.parse.unquote(raw))
        if not path.exists():
            raise MoodtagError(f"Thumbnail path does not exist for {item_id}: {path}")
        return path

    def item_info(self, item_id: str) -> EagleItem:
        query = urllib.parse.urlencode({"id": item_id})
        data = http_request(
            "GET", url_join(self.base_url, f"/api/item/info?{query}"), timeout=10
        )
        self._expect_success(data, "item info")
        return parse_item(data.get("data", {}))

    def update_item(
        self,
        item_id: str,
        *,
        tags: list[str] | None = None,
        annotation: str | None = None,
    ) -> None:
        body: dict[str, Any] = {"id": item_id}
        if tags is not None:
            body["tags"] = tags
        if annotation is not None:
            body["annotation"] = annotation
        data = http_request(
            "POST",
            url_join(self.base_url, "/api/item/update"),
            json_body=body,
            timeout=30,
        )
        self._expect_success(data, "item update")

    @staticmethod
    def _expect_success(data: Any, label: str) -> None:
        if not isinstance(data, dict) or data.get("status") != "success":
            raise MoodtagError(
                f"Eagle {label} failed: {redact(json.dumps(data)[:800])}"
            )


def parse_item(raw: dict[str, Any]) -> EagleItem:
    return EagleItem(
        id=str(raw.get("id", "")).strip(),
        name=str(raw.get("name", "")).strip(),
        ext=str(raw.get("ext", "")).strip().lower().lstrip("."),
        tags=[str(tag) for tag in raw.get("tags", []) if str(tag).strip()],
        folders=[
            str(folder) for folder in raw.get("folders", []) if str(folder).strip()
        ],
        annotation=str(raw.get("annotation", "") or ""),
        width=raw.get("width"),
        height=raw.get("height"),
        size=raw.get("size"),
        palettes=[
            palette
            for palette in (raw.get("palettes") or [])
            if isinstance(palette, dict)
        ],
        rating=(int(raw["star"]) if isinstance(raw.get("star"), int | float) else None),
    )


def normalize_board_query(query: str) -> str:
    normalized = query.strip().strip("/").replace("\\", "/")
    if not normalized:
        return ""
    if normalized.lower().startswith("folder/"):
        path_id = normalized.split("/", 1)[1].strip("/")
        if path_id:
            return path_id
    parts = urllib.parse.urlsplit(normalized)
    if parts.scheme and parts.netloc:
        params = urllib.parse.parse_qs(parts.query)
        for key in ("id", "folderId", "folder_id"):
            values = params.get(key)
            if values:
                candidate = values[0].strip()
                if candidate:
                    return candidate
        path_tail = parts.path.rstrip("/").split("/")[-1].strip()
        if path_tail and path_tail.lower() != "folder":
            return path_tail
    return normalized


def resolve_board(query: str, boards: list[Board]) -> Board:
    normalized = normalize_board_query(query)
    if not normalized:
        raise MoodtagError("Missing --board value")
    by_id = [board for board in boards if board.id == normalized]
    if by_id:
        return by_id[0]

    candidates = find_board_candidates(normalized, boards)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        lines = [f"- {board.path} ({board.id})" for board in candidates[:20]]
        raise MoodtagError(
            "Board name is ambiguous. Use a folder id:\n" + "\n".join(lines)
        )
    raise MoodtagError(f"Board not found: {query}")


def find_board_candidates(query: str, boards: list[Board]) -> list[Board]:
    lowered = query.lower()
    path_matches = [b for b in boards if b.path.lower() == lowered]
    if path_matches:
        return dedupe_boards(path_matches)

    parts = lowered.split("/")
    if len(parts) > 1 and parts[0] in {"moodboard", "moodboards", "board", "boards"}:
        stripped = "/".join(parts[1:])
        path_matches = [b for b in boards if b.path.lower() == stripped]
        if path_matches:
            return dedupe_boards(path_matches)

    name_matches = [b for b in boards if b.name.lower() == lowered]
    return dedupe_boards(name_matches)


def dedupe_boards(boards: list[Board]) -> list[Board]:
    out: list[Board] = []
    seen: set[str] = set()
    for board in boards:
        if board.id not in seen:
            out.append(board)
            seen.add(board.id)
    return out


def descendant_boards(board: Board, boards: list[Board]) -> list[Board]:
    by_parent: dict[str, list[Board]] = {}
    for candidate in boards:
        if candidate.id == board.id:
            continue
        parent = candidate.parent
        if not parent:
            continue
        by_parent.setdefault(parent, []).append(candidate)

    result: list[Board] = []
    queue = deque(by_parent.get(board.id, []))
    seen = {board.id}
    while queue:
        current = queue.popleft()
        if current.id in seen:
            continue
        seen.add(current.id)
        result.append(current)
        queue.extend(by_parent.get(current.id, []))
    return result


def board_scope_boards(
    board: Board, boards: list[Board], *, recursive: bool
) -> list[Board]:
    if not recursive:
        return [board]
    return [board, *descendant_boards(board, boards)]


def dedupe_items(items: list[EagleItem]) -> list[EagleItem]:
    out: list[EagleItem] = []
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            continue
        out.append(item)
        seen.add(item.id)
    return out


def load_board_scope(
    eagle: Any,
    board_query: str,
    *,
    recursive: bool = True,
    max_board_items: int = DEFAULT_MAX_BOARD_ITEMS,
    rating: int | None = None,
    shape: str = "",
) -> BoardScope:
    boards = eagle.boards()
    board = resolve_board(board_query, boards)
    scope_folders: list[BoardScopeFolder] = []
    all_items: list[EagleItem] = []
    for scope_board in board_scope_boards(board, boards, recursive=recursive):
        filters: dict[str, Any] = {}
        if rating is not None:
            filters["rating"] = rating
        if shape:
            filters["shape"] = shape
        folder_items = eagle.list_items(scope_board.id, **filters)
        scope_folders.append(
            BoardScopeFolder(board=scope_board, item_count=len(folder_items))
        )
        all_items.extend(folder_items)
    items = dedupe_items(all_items)
    if max_board_items >= 0 and len(items) > max_board_items:
        raise MoodtagError(
            f"Board scope has {len(items)} items across {len(scope_folders)} folders, "
            f"exceeding --max-board-items {max_board_items}. "
            "Pass a larger --max-board-items value if this is intentional."
        )
    return BoardScope(board=board, folders=scope_folders, items=items)


def resolve_item_scope(eagle: Any, scope_input: ScopeInput) -> ResolvedScope:
    """Resolve a fixed, metadata-bearing Eagle scope snapshot."""
    if scope_input.selected:
        selected_filters: dict[str, Any] = {"selected": True}
        if scope_input.rating is not None:
            selected_filters["rating"] = scope_input.rating
        if scope_input.shape:
            selected_filters["shape"] = scope_input.shape
        items = eagle.list_items("", **selected_filters)
        source = "selected"
    elif scope_input.library:
        library_filters: dict[str, Any] = {}
        if scope_input.rating is not None:
            library_filters["rating"] = scope_input.rating
        if scope_input.shape:
            library_filters["shape"] = scope_input.shape
        count_items = getattr(eagle, "count_items", None)
        total = count_items("", **library_filters) if callable(count_items) else None
        if not isinstance(total, int) or isinstance(total, bool):
            total = None
        if (
            total is not None
            and scope_input.max_items >= 0
            and total > scope_input.max_items
        ):
            if not scope_input.tags:
                raise MoodtagError(
                    f"Entire library has {total:,} items, exceeding "
                    f"--max-board-items {scope_input.max_items:,}. Add filters or "
                    "increase --max-board-items if this is intentional."
                )
        items = eagle.list_items(
            "",
            **library_filters,
            **(
                {
                    "required_tags": scope_input.tags,
                    "max_matches": scope_input.max_items,
                }
                if scope_input.tags and scope_input.max_items >= 0
                else {}
            ),
        )
        source = "Entire library"
        library_info = getattr(eagle, "library_info", None)
        if callable(library_info):
            with contextlib.suppress(Exception):
                info = library_info()
                library = info.get("library") if isinstance(info, dict) else None
                name = (
                    str(library.get("name") or "").strip()
                    if isinstance(library, dict)
                    else ""
                )
                if name:
                    source = name
    else:
        if not scope_input.folder:
            raise MoodtagError("A folder or selected-item scope is required")
        board_scope = load_board_scope(
            eagle,
            scope_input.folder,
            recursive=scope_input.recursive,
            max_board_items=scope_input.max_items,
            rating=scope_input.rating,
            shape=scope_input.shape,
        )
        items = board_scope.items
        source = board_scope.board.path
    required = [tag.casefold() for tag in scope_input.tags]
    if required:
        items = [
            item
            for item in items
            if all(
                any(existing.casefold() == tag for existing in item.tags)
                for tag in required
            )
        ]
    items = sorted(dedupe_items(items), key=lambda item: item.id)
    if (
        scope_input.library
        and scope_input.max_items >= 0
        and len(items) > scope_input.max_items
    ):
        raise MoodtagError(
            f"Entire library scope has {len(items)} matching items, exceeding "
            f"--max-board-items {scope_input.max_items}. Add filters or increase "
            "--max-board-items if this is intentional."
        )
    return ResolvedScope(source=source, items=items)


def print_scope_summary(scope: BoardScope) -> None:
    mode = "recursive" if len(scope.folders) > 1 else "single-folder"
    print(f"Scope: {mode}, {len(scope.folders)} folders")
    if len(scope.folders) > 1:
        print("Folders:")
        for folder in scope.folders:
            print(
                f"- {folder.board.path} ({folder.board.id}): {folder.item_count} items"
            )


def has_moodboard_notes(annotation: str) -> bool:
    return has_analysis_annotation(annotation)


def analysis_item_status(item: EagleItem) -> str:
    return analysis_status(item.annotation)


def merge_item_tags(existing: list[str], generated: list[str]) -> list[str]:
    """Keep user order and append new AI tags without case-insensitive duplicates."""
    merged: list[str] = []
    seen: set[str] = set()
    for tag in [*existing, *generated]:
        clean = str(tag).strip()
        key = clean.casefold()
        if clean and key not in seen:
            merged.append(clean)
            seen.add(key)
    return merged


def compose_item_metadata(
    item: EagleItem, *, tags: list[str], annotation: str
) -> tuple[list[str], str]:
    """Merge generated output into the latest Eagle metadata safely."""
    return (
        merge_item_tags(item.tags, tags),
        replace_analysis_annotation(item.annotation, annotation),
    )


def write_analysis_result(
    eagle: Any,
    result: TagItemResult,
    *,
    skip_existing: bool = False,
) -> str:
    """Refresh one item immediately before writing and return changed/skipped."""
    item_info = getattr(eagle, "item_info", None)
    latest = item_info(result.item.id) if callable(item_info) else result.item
    status = analysis_item_status(latest)
    if skip_existing and status == "valid":
        return "skipped"
    if status == "malformed":
        raise MoodtagError(
            f"Cannot safely update {latest.name or latest.id}: malformed Moodtag annotation"
        )
    tags, annotation = compose_item_metadata(
        latest, tags=result.tags, annotation=result.annotation
    )
    eagle.update_item(latest.id, tags=tags, annotation=annotation)
    return "changed"


def replace_notes_block(existing: str, block: str) -> str:
    return replace_analysis_annotation(existing, block)


def remove_notes_block(existing: str) -> str:
    return remove_analysis_annotation(existing)


def extract_notes_summary(annotation: str) -> str:
    return extract_brief(annotation)


def flatten_taxonomy(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for tags in taxonomy.values():
        for tag in tags:
            allowed[tag.lower()] = tag
    return allowed


def locate_original_from_thumbnail(thumbnail: Path, item: EagleItem) -> Path:
    return locate_original_in_info_dir(thumbnail.parent, item)


def unsupported_media_reason(item: EagleItem) -> str | None:
    extension = item.ext.strip().lower().lstrip(".")
    if f".{extension}" in SUPPORTED_ORIGINAL_EXTS:
        return None
    return f"unsupported media type: {extension or 'unknown'}"


def locate_original_in_info_dir(info_dir: Path, item: EagleItem) -> Path:
    if not info_dir.exists() or not info_dir.is_dir():
        raise MoodtagError(f"Item directory not found for {item.id}: {info_dir}")

    preferred_ext = f".{item.ext.lower()}" if item.ext else ""
    candidates: list[Path] = []
    for path in info_dir.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == "metadata.json" or "_thumbnail" in lower:
            continue
        if path.suffix.lower() not in SUPPORTED_ORIGINAL_EXTS:
            continue
        candidates.append(path)
    if not candidates:
        raise MoodtagError(f"No original image file found in {info_dir}")
    exact = [p for p in candidates if p.suffix.lower() == preferred_ext]
    if exact:
        candidates = exact
    name_matches = [p for p in candidates if p.stem == item.name]
    if name_matches:
        return name_matches[0]
    return max(candidates, key=lambda p: p.stat().st_size)


@contextlib.contextmanager
def temporary_preview(source: Path, *, image_edge: int) -> Iterator[Preview]:
    if image_edge < 256:
        raise MoodtagError("--image-edge must be at least 256")
    preview_path = Path(tempfile.mkstemp(prefix="moodtag-", suffix=".jpg")[1])
    try:
        preview = create_preview(source, preview_path, image_edge=image_edge)
        yield preview
    finally:
        with contextlib.suppress(FileNotFoundError):
            preview_path.unlink()


def create_preview(source: Path, dest: Path, *, image_edge: int) -> Preview:
    try:
        return create_preview_with_pillow(source, dest, image_edge=image_edge)
    except ImportError as exc:
        if shutil.which("sips"):
            return create_preview_with_sips(source, dest, image_edge=image_edge)
        raise MoodtagError(
            "Image resizing requires Pillow. Install it with `python -m pip install Pillow`."
        ) from exc


def create_preview_with_pillow(source: Path, dest: Path, *, image_edge: int) -> Preview:
    from PIL import Image, ImageOps  # type: ignore[import-not-found]

    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img)
        source_width, source_height = img.size
        width, height = scaled_size(source_width, source_height, image_edge)
        if img.size != (width, height):
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        if img.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.getchannel("A"))
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dest, format="JPEG", quality=88, optimize=True)
    return Preview(dest, source, source_width, source_height, width, height)


def create_preview_with_sips(source: Path, dest: Path, *, image_edge: int) -> Preview:
    source_width, source_height = sips_dimensions(source)
    width, height = scaled_size(source_width, source_height, image_edge)
    command = ["sips", "-s", "format", "jpeg"]
    if source_width >= source_height:
        command += ["--resampleWidth", str(image_edge)]
    else:
        command += ["--resampleHeight", str(image_edge)]
    command += [str(source), "--out", str(dest)]
    proc = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0 or not dest.exists():
        raise MoodtagError(f"sips failed to create preview: {proc.stderr.strip()}")
    return Preview(dest, source, source_width, source_height, width, height)


def sips_dimensions(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise MoodtagError(f"sips cannot read image dimensions: {proc.stderr.strip()}")
    width_match = re.search(r"pixelWidth:\s*(\d+)", proc.stdout)
    height_match = re.search(r"pixelHeight:\s*(\d+)", proc.stdout)
    if not width_match or not height_match:
        raise MoodtagError(f"sips did not return dimensions for {path}")
    return int(width_match.group(1)), int(height_match.group(1))


def scaled_size(width: int, height: int, edge: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise MoodtagError("Invalid image dimensions")
    if width >= height:
        return edge, max(1, round(height * edge / width))
    return max(1, round(width * edge / height)), edge


class VisionClient(CoreVisionClient):
    def analyze(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        retries: int,
        max_tags: int = DEFAULT_MAX_TAGS,
    ) -> MoodtagAnalysis:
        return super().analyze(image, taxonomy, retries=retries, max_tags=max_tags)


class MockVisionClient:
    def __init__(self, model: str = "mock-vision", profile: str = "editorial") -> None:
        self.model = model
        self.profile = resolve_profile(profile).id
        self.protocol = "mock"
        self.last_endpoint_protocol = "mock"
        self.last_endpoint_base_url = "mock://local"
        self.last_endpoint_model = model
        self.last_attempts: list[Any] = []

    def analyze(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        retries: int,
        max_tags: int = DEFAULT_MAX_TAGS,
    ) -> MoodtagAnalysis:
        del image, retries
        first_tags = [tags[0] for _, tags in list(taxonomy.items())[:3] if tags]
        result = normalize_analysis_json(
            {
                "brief": "A test subject stands against a clean backdrop with simple props.",
                "elements": [
                    "test subject",
                    "sample outfit",
                    "simple props",
                    "clean backdrop",
                    "neutral palette",
                ],
                "use": "Reference for testing Moodtag tagging, composition, and lighting notes.",
                "key": "Clear visual information for checking tag and note extraction.",
                "camera": "Centered medium shot with a standard-lens perspective.",
                "light_color": "Soft directional light with a neutral color palette.",
                "tags": first_tags,
                "use_intents": ["lighting_reference", "pose_reference"],
            },
            taxonomy=taxonomy,
            max_tags=max_tags,
        )
        self.last_endpoint_protocol = "mock"
        self.last_endpoint_base_url = "mock://local"
        self.last_endpoint_model = self.model
        self.last_attempts = [
            {
                "protocol": "mock",
                "base_url": "mock://local",
                "model": self.model,
                "ok": True,
                "elapsed_ms": 0,
                "status": None,
                "error": "",
            }
        ]
        return result


def file_to_data_url(path: Path, mimetype: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"


def build_prompt(profile: str = "editorial") -> str:
    from moodtag_core.prompts import render_user_prompt

    return render_user_prompt(load_profile_taxonomy(profile), profile=profile)


def extract_chat_content_json(data: Any) -> dict[str, Any]:
    from moodtag_core.response import extract_assistant_content, parse_json_content

    return parse_json_content(extract_assistant_content(data))


def normalize_model_result(
    data: Any,
    taxonomy: dict[str, list[str]] | None = None,
    max_tags: int = DEFAULT_MAX_TAGS,
) -> MoodtagAnalysis:
    taxonomy = taxonomy or load_profile_taxonomy()
    try:
        if isinstance(data, str):
            return parse_analysis_response(
                {"choices": [{"message": {"content": data}}]},
                taxonomy=taxonomy,
                max_tags=max_tags,
            )
        if isinstance(data, dict) and ("choices" in data or "output" in data):
            return parse_analysis_response(data, taxonomy=taxonomy, max_tags=max_tags)
        return normalize_analysis_json(data, taxonomy=taxonomy, max_tags=max_tags)
    except CoreError as exc:
        raise MoodtagError(str(exc)) from exc


def validate_model_result(result: MoodtagAnalysis) -> None:
    if not all(
        [
            result.brief,
            result.elements,
            result.use,
            result.key,
            result.camera,
            result.light_color,
        ]
    ):
        raise MoodtagError("Model result missing required annotation fields")


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def reconcile_tags(
    result: MoodtagAnalysis, taxonomy: dict[str, list[str]], max_tags: int
) -> tuple[list[str], list[str]]:
    del taxonomy
    return result.tags[:max_tags], result.rejected_tags


def build_notes_block(result: MoodtagAnalysis) -> str:
    return build_annotation_block(result)


def make_vision_client(
    args: argparse.Namespace,
) -> VisionClient | OllamaVisionClient | MockVisionClient:
    if getattr(args, "mock_model", False):
        return MockVisionClient(args.model or "mock-vision", profile=args.profile)
    model = str(getattr(args, "model", "")).strip()
    base_url = str(getattr(args, "base_url", "")).strip()
    source = str(getattr(args, "source", "openai-compatible") or "openai-compatible")
    if source == "ollama":
        return OllamaVisionClient(
            base_url=base_url or "http://127.0.0.1:11434",
            model=model,
            profile=args.profile,
            preset=str(getattr(args, "ollama_preset", "qwen-instruct")),
            options={"num_predict": args.max_tokens},
        )
    api_key = os.environ.get("MOODTAG_API_KEY", "").strip()
    missing = [
        name for name, value in (("base URL", base_url), ("model", model)) if not value
    ]
    if missing or not api_key:
        details = ", ".join(missing)
        if not api_key:
            details = f"{details}; MOODTAG_API_KEY" if details else "MOODTAG_API_KEY"
        raise MoodtagError(
            f"Model setup incomplete ({details}). Run `moodtag config model`."
        )
    try:
        protocol = protocol_for_model(model)
    except CoreError as exc:
        raise MoodtagError(str(exc)) from exc
    return VisionClient(
        protocol=protocol,
        base_url=base_url,
        model=model,
        api_key=api_key,
        response_format=not args.no_response_format,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        profile=args.profile,
    )


def ensure_model_setup(args: argparse.Namespace) -> None:
    if getattr(args, "source", "") == "ollama":
        if not getattr(args, "model", ""):
            raise MoodtagError(
                "Ollama model is not configured. Run `moodtag config model`."
            )
        return
    complete = bool(
        getattr(args, "base_url", "")
        and getattr(args, "model", "")
        and os.environ.get("MOODTAG_API_KEY", "").strip()
    )
    if complete:
        try:
            normalize_base_url(args.base_url, protocol_for_model(args.model))
        except CoreError as exc:
            raise MoodtagError(str(exc)) from exc
        return
    if not sys.stdin.isatty():
        raise MoodtagError("Model setup incomplete. Run `moodtag config model`.")
    values = _setup_prompt(Printer(), load_user_config())
    source = values.get("source", "openai-compatible")
    _persist_setup(values)
    args.base_url = values["base_url"]
    args.model = values["model"]
    args.source = source
    args.ollama_preset = values.get("ollama_preset", "qwen-instruct")
    if "MOODTAG_API_KEY" not in os.environ:
        os.environ["MOODTAG_API_KEY"] = values["api_key"]


def validate_board_scope_args(args: argparse.Namespace) -> None:
    if args.max_board_items < -1:
        raise MoodtagError("--max-board-items must be at least -1")
    if not getattr(args, "board", ""):
        raise MoodtagError("--board is required for this command")


def validate_tag_args(args: argparse.Namespace) -> None:
    selected = bool(getattr(args, "selected", False))
    library = bool(getattr(args, "library", False))
    board = str(getattr(args, "board", "") or "")
    if selected and (board or library):
        raise MoodtagError("Use only one scope: --board, --selected, or --library")
    if library and board:
        raise MoodtagError("Use only one scope: --board, --selected, or --library")
    if not selected and not library and not board:
        if (
            getattr(args, "tags", [])
            or getattr(args, "rating", None) is not None
            or getattr(args, "shape", None)
        ):
            args.library = True
            library = True
        else:
            raise MoodtagError("Provide --board, --selected, or --library")
    if not selected and not library:
        validate_board_scope_args(args)
    elif args.max_board_items < -1:
        raise MoodtagError("--max-board-items must be at least -1")
    if getattr(args, "rating", None) is not None and not 0 <= args.rating <= 5:
        raise MoodtagError("--rating must be between 0 and 5")
    try:
        args.profile = resolve_profile(args.profile).id
    except CoreError as exc:
        raise MoodtagError(str(exc)) from exc
    if args.image_edge < 256:
        raise MoodtagError("--image-edge must be at least 256")
    if args.concurrency < 1:
        raise MoodtagError("--concurrency must be at least 1")
    if args.max_tags < 1:
        raise MoodtagError("--max-tags must be at least 1")
    if args.limit < 0:
        raise MoodtagError("--limit must be at least 0")
    if args.retries < 0:
        raise MoodtagError("--retries must be at least 0")
    if args.temperature < 0:
        raise MoodtagError("--temperature must be at least 0")
    if args.top_p <= 0 or args.top_p > 1:
        raise MoodtagError("--top-p must be greater than 0 and at most 1")
    if args.max_tokens < MIN_MAX_TOKENS:
        raise MoodtagError(f"--max-tokens must be at least {MIN_MAX_TOKENS}")


def analyze_tag_item(
    *,
    index: int,
    item: EagleItem,
    eagle: Any,
    vision: VisionClient | MockVisionClient,
    image_root: Path | None = None,
    taxonomy: dict[str, list[str]],
    image_edge: int,
    retries: int,
    max_tags: int,
) -> TagItemResult:
    item_started = time.monotonic()
    clear_endpoint_trace(vision)
    source_lookup_ms = 0
    preview_ms = 0
    vision_ms = 0
    source_strategy = ""
    source_started = item_started
    preview_started: float | None = None
    vision_started: float | None = None
    source_lookup_finished = False
    preview_finished = False
    vision_finished = False
    try:
        source_started = time.monotonic()
        original: Path | None = None
        if image_root is not None:
            with contextlib.suppress(Exception):
                original = locate_original_in_info_dir(
                    image_root / f"{item.id}.info", item
                )
                source_strategy = "library_root"
        if original is None:
            source_strategy = "thumbnail_fallback"
            original = locate_original_from_thumbnail(
                eagle.thumbnail_path(item.id), item
            )
        source_lookup_ms = elapsed_ms_since(source_started)
        source_lookup_finished = True

        preview_started = time.monotonic()
        with temporary_preview(original, image_edge=image_edge) as preview:
            preview_ms = elapsed_ms_since(preview_started)
            preview_finished = True
            vision_started = time.monotonic()
            result = vision.analyze(
                preview.path,
                taxonomy,
                retries=retries,
                max_tags=max_tags,
            )
            vision_ms = elapsed_ms_since(vision_started)
            vision_finished = True
        validate_model_result(result)
        tags, _rejected = reconcile_tags(result, taxonomy, max_tags=max_tags)
        analysis_total_ms = elapsed_ms_since(item_started)
        return TagItemResult(
            index=index,
            item=item,
            tags=tags,
            annotation=build_notes_block(result),
            model_endpoint=model_endpoint_record(vision),
            attempts=model_attempt_records(vision),
            timings_ms={
                "source_lookup_ms": source_lookup_ms,
                "preview_ms": preview_ms,
                "vision_ms": vision_ms,
                "analysis_total_ms": analysis_total_ms,
            },
            source_strategy=source_strategy,
            elapsed_ms=analysis_total_ms,
        )
    except Exception as exc:  # noqa: BLE001 - per-item isolation
        if not source_lookup_finished:
            source_lookup_ms = elapsed_ms_since(source_started)
        if preview_started is not None and not preview_finished:
            preview_ms = elapsed_ms_since(preview_started)
        if vision_started is not None and not vision_finished:
            vision_ms = elapsed_ms_since(vision_started)
        analysis_total_ms = elapsed_ms_since(item_started)
        return TagItemResult(
            index=index,
            item=item,
            model_endpoint=model_endpoint_record(vision),
            attempts=model_attempt_records(vision),
            timings_ms={
                "source_lookup_ms": source_lookup_ms,
                "preview_ms": preview_ms,
                "vision_ms": vision_ms,
                "analysis_total_ms": analysis_total_ms,
            },
            source_strategy=source_strategy,
            elapsed_ms=analysis_total_ms,
            error=exc,
        )


def run_tag_analysis(
    *,
    work_items: list[tuple[int, EagleItem]],
    eagle: Any,
    vision: VisionClient | MockVisionClient,
    vision_factory: Callable[[], VisionClient | MockVisionClient] | None = None,
    image_root: Path | None = None,
    taxonomy: dict[str, list[str]],
    image_edge: int,
    retries: int,
    max_tags: int,
    concurrency: int,
) -> Iterator[TagItemResult]:
    if concurrency <= 1 or len(work_items) <= 1:
        for index, item in work_items:
            yield analyze_tag_item(
                index=index,
                item=item,
                eagle=eagle,
                vision=vision,
                image_root=image_root,
                taxonomy=taxonomy,
                image_edge=image_edge,
                retries=retries,
                max_tags=max_tags,
            )
        return

    workers = min(concurrency, len(work_items))
    futures: dict[concurrent.futures.Future[TagItemResult], int] = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    next_submit = 0

    def submit_ready() -> None:
        nonlocal next_submit
        while next_submit < len(work_items) and len(futures) < workers:
            index, item = work_items[next_submit]
            worker_vision = vision_factory() if vision_factory is not None else vision
            future = executor.submit(
                analyze_tag_item,
                index=index,
                item=item,
                eagle=eagle,
                vision=worker_vision,
                image_root=image_root,
                taxonomy=taxonomy,
                image_edge=image_edge,
                retries=retries,
                max_tags=max_tags,
            )
            futures[future] = next_submit
            next_submit += 1

    try:
        submit_ready()
        while futures:
            done, _pending = concurrent.futures.wait(
                futures, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                futures.pop(future)
                yield future.result()
            submit_ready()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def command_status(args: argparse.Namespace) -> int:
    validate_board_scope_args(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    processed = [item for item in items if has_moodboard_notes(item.annotation)]
    printer = Printer()
    printer.emit(f"Board: {board.path}")
    printer.emit(f"Items: {len(items)}")
    printer.emit(f"Processed: {len(processed)}")
    printer.emit(f"Pending: {len(items) - len(processed)}")
    if args.verbose:
        for item in items:
            status = "processed" if has_moodboard_notes(item.annotation) else "pending"
            printer.emit(f"{status}\t{item.id}\t{item.name}")
    return 0


def build_context_markdown(
    board: Board,
    items: list[EagleItem],
    *,
    include_pending: bool = False,
    source_paths: dict[str, Path] | None = None,
) -> str:
    rows, skipped_pending = context_rows(items, include_pending=include_pending)
    source_paths = source_paths or {}

    lines = [
        f"# Moodboard Context: {board.path}",
        "",
        f"Items: {len(items)}",
        f"Exported: {len(rows)}",
        f"Pending skipped: {skipped_pending}",
        "",
    ]

    label_width = max(2, len(str(max(0, len(rows) - 1))))
    for index, (item, fields, complete) in enumerate(rows):
        lines.append(f"## {index:0{label_width}d}")
        lines.append(
            format_context_metadata(
                item,
                fields,
                source_path=source_paths.get(item.id),
            )
        )
        if not complete:
            lines.append("Status: pending")
        lines.append("Tags: " + format_tags(item.tags))
        palette = format_palettes(item.palettes)
        if palette:
            lines.append("Palette: " + palette)
        lines.append("")
        for label in ANNOTATION_LABEL_ORDER:
            if label == "Brief":
                continue
            value = one_line(fields.get(label, ""))
            if value or include_pending:
                lines.append(f"{label}: {value or '-'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def context_rows(
    items: list[EagleItem],
    *,
    include_pending: bool = False,
) -> tuple[list[tuple[EagleItem, dict[str, str], bool]], int]:
    rows: list[tuple[EagleItem, dict[str, str], bool]] = []
    skipped_pending = 0
    for item in items:
        fields = parse_annotation_fields(item.annotation)
        complete = all(fields.get(label) for label in ANNOTATION_LABEL_ORDER)
        if not complete and not include_pending:
            skipped_pending += 1
            continue
        rows.append((item, fields, complete))
    return rows, skipped_pending


def format_context_metadata(
    item: EagleItem,
    fields: dict[str, str],
    *,
    source_path: Path | None = None,
) -> str:
    parts = [format_image_link(item, fields, source_path=source_path), f"`{item.id}`"]
    dimensions = format_dimensions(item)
    if dimensions:
        parts.append(dimensions)
    size = format_file_size(item.size)
    if size:
        parts.append(size)
    return " · ".join(parts)


def format_image_link(
    item: EagleItem,
    fields: dict[str, str],
    *,
    source_path: Path | None = None,
) -> str:
    display_name = context_image_display_name(item, fields)
    if not source_path:
        return display_name
    return f"[{markdown_link_text(display_name)}](<{source_path}>)"


def context_image_display_name(item: EagleItem, fields: dict[str, str]) -> str:
    stem = one_line(fields.get("Brief") or item.name or item.id).rstrip("。.!！?？")
    ext = one_line(item.ext)
    if not ext:
        return stem
    suffix = "." + ext.lower()
    if stem.lower().endswith(suffix):
        return stem
    return f"{stem}.{ext}"


def markdown_link_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def format_dimensions(item: EagleItem) -> str:
    if item.width and item.height:
        return f"{item.width}x{item.height}"
    return ""


def format_file_size(size: int | None) -> str:
    if not isinstance(size, int) or size <= 0:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{round(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def format_tags(tags: list[str]) -> str:
    return " | ".join(one_line(tag) for tag in tags) or "-"


def format_palettes(palettes: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for palette in palettes:
        color = palette.get("color")
        if not (
            isinstance(color, list)
            and len(color) == 3
            and all(
                isinstance(channel, int) and 0 <= channel <= 255 for channel in color
            )
        ):
            continue
        ratio = format_palette_ratio(palette.get("ratio"))
        color_text = "#{:02x}{:02x}{:02x}".format(*color)
        values.append(f"{color_text} {ratio}" if ratio else color_text)
    return " | ".join(values)


def format_palette_ratio(value: Any) -> str:
    if not isinstance(value, int | float):
        return ""
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def one_line(value: str) -> str:
    return " ".join(str(value or "").split())


def export_source_paths(eagle: Any, items: list[EagleItem]) -> dict[str, Path]:
    image_root = eagle_library_images_root(eagle)
    paths: dict[str, Path] = {}
    for item in items:
        path: Path | None = None
        if image_root is not None:
            with contextlib.suppress(Exception):
                path = locate_original_in_info_dir(image_root / f"{item.id}.info", item)
        if path is None:
            with contextlib.suppress(Exception):
                path = locate_original_from_thumbnail(
                    eagle.thumbnail_path(item.id), item
                )
        if path is not None:
            paths[item.id] = path
    return paths


def eagle_library_images_root(eagle: Any) -> Path | None:
    with contextlib.suppress(Exception):
        data = eagle.library_info()
        if not isinstance(data, dict):
            return None
        library = data.get("library")
        if not isinstance(library, dict):
            return None
        raw_path = str(library.get("path") or "").strip()
        if raw_path:
            return Path(raw_path).expanduser() / "images"
    return None


def command_export_context(args: argparse.Namespace) -> int:
    validate_board_scope_args(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    rows, _skipped_pending = context_rows(items, include_pending=args.include_pending)
    source_paths = export_source_paths(
        eagle, [item for item, _fields, _complete in rows]
    )
    markdown = build_context_markdown(
        board,
        items,
        include_pending=args.include_pending,
        source_paths=source_paths,
    )
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        Printer().emit(f"Wrote {args.output}", state="success")
    else:
        print(markdown, end="")
    return 0


def format_model_endpoint(vision: Any) -> str:
    record = model_endpoint_record(vision)
    if not record:
        return "unavailable"
    return (
        f"protocol={record.get('protocol', '')} model={record.get('model', '')} "
        f"host={endpoint_display_host(record.get('base_url', ''))}"
    )


def endpoint_display_host(base_url: str) -> str:
    parts = urllib.parse.urlsplit(str(base_url or ""))
    if parts.netloc:
        return parts.netloc
    return str(base_url or "")


def image_destination_message(record: dict[str, Any]) -> str:
    if record.get("protocol") == "ollama":
        return (
            "Images go to the configured loopback Ollama API; "
            "server-side inference locality cannot be independently verified."
        )
    return (
        "Images will be sent to the configured model endpoint "
        f"({endpoint_display_host(record.get('base_url', ''))})."
    )


def model_endpoint_records(vision: Any) -> list[dict[str, Any]]:
    record = model_endpoint_record(vision)
    if not record:
        return []
    return [
        {
            "protocol": record["protocol"],
            "base_url": record["base_url"],
            "model": record["model"],
        }
    ]


def model_endpoint_summary(vision: Any) -> str:
    record = model_endpoint_record(vision)
    return model_endpoint_record_summary(record)


def model_endpoint_record_summary(record: dict[str, Any]) -> str:
    if not record:
        return "model=unknown"
    return (
        f"protocol={record['protocol']} model={record['model']} "
        f"host={endpoint_display_host(record['base_url'])}"
    )


def model_endpoint_record(vision: Any) -> dict[str, Any]:
    protocol = str(
        getattr(vision, "last_endpoint_protocol", "")
        or getattr(vision, "protocol", "")
        or ""
    )
    base_url = str(getattr(vision, "last_endpoint_base_url", "") or "")
    model = str(getattr(vision, "last_endpoint_model", "") or "")
    if not protocol and not base_url and not model:
        return {}
    response = getattr(vision, "last_response", None)
    metadata = getattr(response, "metadata", None)
    response_metadata: dict[str, Any] = {}
    if metadata is not None:
        response_metadata = {
            "response_id": getattr(metadata, "response_id", None),
            "request_id": getattr(metadata, "request_id", None),
            "client_request_id": getattr(metadata, "client_request_id", None),
            "status": getattr(metadata, "status", None),
            "http_status": getattr(metadata, "http_status", None),
            "usage": dict(getattr(metadata, "usage", {}) or {}),
            "usage_normalized": normalize_usage(getattr(metadata, "usage", {})),
            "headers": dict(getattr(metadata, "headers", {}) or {}),
            "elapsed_ms": getattr(metadata, "elapsed_ms", None),
        }
    return {
        "protocol": protocol,
        "base_url": base_url,
        "model": model,
        "response": response_metadata,
    }


def model_attempt_records(vision: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for attempt in getattr(vision, "last_attempts", []) or []:
        if isinstance(attempt, dict):
            records.append(
                {
                    "protocol": attempt.get("protocol", ""),
                    "base_url": attempt.get("base_url", ""),
                    "model": attempt.get("model", ""),
                    "ok": bool(attempt.get("ok")),
                    "elapsed_ms": attempt.get("elapsed_ms", 0),
                    "status": attempt.get("status"),
                    "error": redact(str(attempt.get("error", ""))),
                    "submission_state": attempt.get("submission_state", "not_sent"),
                    "client_request_id": attempt.get("client_request_id"),
                    "headers": dict(attempt.get("headers", {}) or {}),
                }
            )
            continue
        records.append(
            {
                "protocol": getattr(attempt, "protocol", ""),
                "base_url": getattr(attempt, "base_url", ""),
                "model": getattr(attempt, "model", ""),
                "ok": bool(getattr(attempt, "ok", False)),
                "elapsed_ms": getattr(attempt, "elapsed_ms", 0),
                "status": getattr(attempt, "status", None),
                "error": redact(str(getattr(attempt, "error", ""))),
                "submission_state": getattr(attempt, "submission_state", "not_sent"),
                "client_request_id": getattr(attempt, "client_request_id", None),
                "headers": dict(getattr(attempt, "headers", {}) or {}),
            }
        )
    return records


def clear_endpoint_trace(vision: Any) -> None:
    for name, value in (
        ("last_endpoint_protocol", ""),
        ("last_endpoint_base_url", ""),
        ("last_endpoint_model", ""),
        ("last_attempts", []),
    ):
        with contextlib.suppress(Exception):
            setattr(vision, name, value)


def item_log_record(item: EagleItem, *, index: int, total: int) -> dict[str, Any]:
    return {
        "index": index,
        "total": total,
        "id": item.id,
        "name": item.name,
        "ext": item.ext,
        "width": item.width,
        "height": item.height,
        "size": item.size,
    }


def timing_keys() -> tuple[str, ...]:
    return (
        "source_lookup_ms",
        "preview_ms",
        "vision_ms",
        "analysis_total_ms",
        "write_ms",
    )


def timing_totals_record() -> dict[str, int]:
    return {key: 0 for key in timing_keys()}


def timing_counts_record() -> dict[str, int]:
    return {key: 0 for key in timing_keys()}


def merge_timings(
    timings_ms: dict[str, int], *, write_ms: int | None = None
) -> dict[str, int]:
    merged = {
        key: max(0, int(value))
        for key, value in timings_ms.items()
        if key in set(timing_keys())
    }
    if write_ms is not None:
        merged["write_ms"] = max(0, int(write_ms))
    return merged


def record_timing_totals(
    timing_totals_ms: dict[str, int],
    timing_item_counts: dict[str, int],
    timings_ms: dict[str, int],
) -> None:
    for key, value in timings_ms.items():
        if key not in timing_totals_ms:
            continue
        timing_totals_ms[key] += max(0, int(value))
        timing_item_counts[key] += 1


def command_guided_tag(args: argparse.Namespace) -> int:
    return _command_guided_tag_v2(args)


def _command_guided_tag_legacy(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    if not getattr(args, "mock_model", False):
        ensure_model_setup(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    if args.limit:
        pending: list[EagleItem] = []
        processed: list[EagleItem] = []
        for item in items:
            if has_moodboard_notes(item.annotation) and not args.force:
                processed.append(item)
            else:
                pending.append(item)
        items = pending[: args.limit] + processed
    if not sys.stdin.isatty():
        raise MoodtagError(
            "Guided main flow requires an interactive terminal. Use `moodtag tag --board ...` for non-interactive runs."
        )
    print(f"Board: {board.path} ({board.id})")
    print_scope_summary(scope)
    print(f"Items: {len(items)}")
    print(f"Protocol: {args.protocol}; Model: {args.model}")
    print("API key: ready")
    print("Overwrite risk: existing tags and annotation will be replaced.")

    if not prompt_yes_no("Start tagging and write these changes?", default=False):
        print("Cancelled. No changes written.")
        return 0

    vision = public_attr("make_vision_client")(args)
    taxonomy = load_profile_taxonomy(args.profile)
    image_root = eagle_library_images_root(eagle)
    run_log = make_tag_run_log()
    print(f"Log: {run_log.path}")
    print(f"Model endpoint: {format_model_endpoint(vision)}")
    run_log.write(
        "run_start",
        command="tag",
        profile=args.profile,
        mode="guided",
        board_query=args.board,
        limit=args.limit,
        force=args.force,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
        image_edge=args.image_edge,
        concurrency=args.concurrency,
        max_tags=args.max_tags,
        retries=args.retries,
        model_endpoint=model_endpoint_records(vision),
    )
    run_log.write(
        "board_loaded",
        board={"id": board.id, "path": board.path, "name": board.name},
        scope=[
            {
                "id": folder.board.id,
                "path": folder.board.path,
                "name": folder.board.name,
                "items": folder.item_count,
            }
            for folder in scope.folders
        ],
        items=len(items),
    )

    changed = 0
    failed = 0
    skipped = 0
    total = len(items)
    action = "write"
    timing_totals_ms = timing_totals_record()
    timing_item_counts = timing_counts_record()

    work_items: list[tuple[int, EagleItem]] = []
    skipped_reasons: dict[int, str] = {}
    for index, item in enumerate(items, start=1):
        if has_moodboard_notes(item.annotation) and not args.force:
            skipped_reasons[index] = "already processed"
        elif reason := unsupported_media_reason(item):
            skipped_reasons[index] = reason
        else:
            work_items.append((index, item))

    probe_result: TagItemResult | None = None
    if work_items:
        probe_index, probe_item = work_items[0]
        probe_result = analyze_tag_item(
            index=probe_index,
            item=probe_item,
            eagle=eagle,
            vision=vision,
            image_root=image_root,
            taxonomy=taxonomy,
            image_edge=args.image_edge,
            retries=args.retries,
            max_tags=args.max_tags,
        )

    if probe_result is not None and isinstance(
        probe_result.error, ProviderAuthenticationError
    ):
        print(
            f"[{probe_result.index}/{total}] failed\t{probe_result.item.id}\t"
            f"{redact(str(probe_result.error))}"
        )
        run_log.write(
            "item_failed",
            item=item_log_record(
                probe_result.item, index=probe_result.index, total=total
            ),
            error=redact(str(probe_result.error)),
            attempts=probe_result.attempts,
            timings_ms=merge_timings(probe_result.timings_ms),
            source_strategy=probe_result.source_strategy,
            elapsed_ms=probe_result.elapsed_ms,
        )
        record_timing_totals(
            timing_totals_ms, timing_item_counts, merge_timings(probe_result.timings_ms)
        )
        run_log.write(
            "run_aborted",
            reason=redact(str(probe_result.error)),
            attempts=probe_result.attempts,
        )
        print(f"Board: {board.path} ({board.id})")
        print_scope_summary(scope)
        print("Failed: 1")
        print("Skipped: 0")
        print("Changed: 0")
        run_log.write(
            "run_complete",
            board={"id": board.id, "path": board.path, "name": board.name},
            changed=changed,
            skipped=0,
            failed=1,
            aborted=True,
            timing_totals_ms=timing_totals_ms,
            timing_item_counts=timing_item_counts,
        )
        return 1

    remaining_work_items = work_items[1:] if probe_result is not None else []
    remaining_results = run_tag_analysis(
        work_items=remaining_work_items,
        eagle=eagle,
        vision=vision,
        vision_factory=(
            lambda: (
                public_attr("make_vision_client")(args)
                if args.concurrency > 1
                else None
            )
        ),
        image_root=image_root,
        taxonomy=taxonomy,
        image_edge=args.image_edge,
        retries=args.retries,
        max_tags=args.max_tags,
        concurrency=args.concurrency,
    )

    def handle_result(result: TagItemResult) -> tuple[int, int]:
        if result.error is not None:
            print(
                f"[{result.index}/{total}] failed\t{result.item.id}\t"
                f"{redact(str(result.error))}"
            )
            run_log.write(
                "item_failed",
                item=item_log_record(result.item, index=result.index, total=total),
                error=redact(str(result.error)),
                attempts=result.attempts,
                timings_ms=merge_timings(result.timings_ms),
                source_strategy=result.source_strategy,
                elapsed_ms=result.elapsed_ms,
            )
            record_timing_totals(
                timing_totals_ms, timing_item_counts, merge_timings(result.timings_ms)
            )
            return 0, 1

        write_started = time.monotonic()
        try:
            write_status = write_analysis_result(
                eagle, result, skip_existing=not args.force
            )
            if write_status == "skipped":
                return 0, 0
        except Exception as exc:  # noqa: BLE001 - per-item isolation
            write_ms = elapsed_ms_since(write_started)
            timings_ms = merge_timings(result.timings_ms, write_ms=write_ms)
            print(
                f"[{result.index}/{total}] failed\t{result.item.id}\t{redact(str(exc))}"
            )
            run_log.write(
                "item_failed",
                item=item_log_record(result.item, index=result.index, total=total),
                error=redact(str(exc)),
                model_endpoint=result.model_endpoint,
                attempts=result.attempts,
                timings_ms=timings_ms,
                source_strategy=result.source_strategy,
                elapsed_ms=result.elapsed_ms,
            )
            record_timing_totals(
                timing_totals_ms,
                timing_item_counts,
                timings_ms,
            )
            return 0, 1
        timings_ms = merge_timings(
            result.timings_ms, write_ms=elapsed_ms_since(write_started)
        )
        record_timing_totals(timing_totals_ms, timing_item_counts, timings_ms)
        endpoint = model_endpoint_record_summary(result.model_endpoint)
        print(
            f"[{result.index}/{total}] {action}\t{result.item.id}\t"
            f"{result.item.name}\t{len(result.tags)} tags\t{endpoint}"
        )
        run_log.write(
            "item_written",
            item=item_log_record(result.item, index=result.index, total=total),
            tags=result.tags,
            annotation_chars=len(result.annotation),
        )
        run_log.write(
            "item_completed",
            item=item_log_record(result.item, index=result.index, total=total),
            action=action,
            changed=True,
            tags=result.tags,
            tag_count=len(result.tags),
            model_endpoint=result.model_endpoint,
            attempts=result.attempts,
            timings_ms=timings_ms,
            source_strategy=result.source_strategy,
            elapsed_ms=result.elapsed_ms,
        )
        return 1, 0

    def emit_skip(index: int, item: EagleItem, reason: str) -> None:
        nonlocal skipped
        skipped += 1
        print(f"[{index}/{total}] skip\t{item.id}\t{item.name}\t{reason}")
        run_log.write(
            "item_skipped",
            item=item_log_record(item, index=index, total=total),
            reason=reason,
        )

    result_iter = iter(remaining_results)
    for index, item in enumerate(items, start=1):
        if reason := skipped_reasons.get(index):
            emit_skip(index, item, reason)
            continue
        result = (
            probe_result
            if probe_result is not None and index == probe_result.index
            else next(result_iter)
        )
        result_changed, result_failed = handle_result(result)
        changed += result_changed
        failed += result_failed

    run_log.write(
        "run_complete",
        board={"id": board.id, "path": board.path, "name": board.name},
        changed=changed,
        skipped=skipped,
        failed=failed,
        aborted=False,
        timing_totals_ms=timing_totals_ms,
        timing_item_counts=timing_item_counts,
    )
    print(f"Changed: {changed}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    return 0 if failed == 0 else 1


def command_tag(args: argparse.Namespace) -> int:
    if getattr(args, "guided_main_flow", False):
        return command_guided_tag(args)
    return _command_tag_v2(args)


def _command_tag_legacy(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    if getattr(args, "guided_main_flow", False):
        return command_guided_tag(args)
    vision = public_attr("make_vision_client")(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    taxonomy = load_profile_taxonomy(args.profile)
    image_root = eagle_library_images_root(eagle)
    run_log = make_tag_run_log()
    print(f"Log: {run_log.path}")
    print(f"Model endpoint: {format_model_endpoint(vision)}")
    run_log.write(
        "run_start",
        command="tag",
        profile=args.profile,
        mode="write" if args.write else "dry-run",
        board_query=args.board,
        limit=args.limit,
        force=args.force,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
        image_edge=args.image_edge,
        concurrency=args.concurrency,
        max_tags=args.max_tags,
        retries=args.retries,
        model_endpoint=model_endpoint_records(vision),
    )
    if args.limit:
        pending: list[EagleItem] = []
        processed: list[EagleItem] = []
        for item in items:
            if has_moodboard_notes(item.annotation) and not args.force:
                processed.append(item)
            else:
                pending.append(item)
        items = pending[: args.limit] + processed
    changed = 0
    failed = 0
    skipped = 0
    total = len(items)
    action = "write" if args.write else "dry-run"
    timing_totals_ms = timing_totals_record()
    timing_item_counts = timing_counts_record()
    run_log.write(
        "board_loaded",
        board={"id": board.id, "path": board.path, "name": board.name},
        scope=[
            {
                "id": folder.board.id,
                "path": folder.board.path,
                "name": folder.board.name,
                "items": folder.item_count,
            }
            for folder in scope.folders
        ],
        items=total,
    )

    def handle_result(result: TagItemResult) -> tuple[int, int]:
        if result.error is not None:
            timings_ms = merge_timings(result.timings_ms)
            record_timing_totals(timing_totals_ms, timing_item_counts, timings_ms)
            print(
                f"[{result.index}/{total}] failed\t{result.item.id}\t"
                f"{redact(str(result.error))}"
            )
            run_log.write(
                "item_failed",
                item=item_log_record(result.item, index=result.index, total=total),
                error=redact(str(result.error)),
                attempts=result.attempts,
                timings_ms=timings_ms,
                source_strategy=result.source_strategy,
                elapsed_ms=result.elapsed_ms,
            )
            if args.fail_fast and not isinstance(
                result.error, ProviderAuthenticationError
            ):
                raise result.error
            return 0, 1

        if args.write:
            write_started = time.monotonic()
            try:
                write_status = write_analysis_result(
                    eagle, result, skip_existing=not args.force
                )
                if write_status == "skipped":
                    return 0, 0
            except Exception as exc:  # noqa: BLE001 - per-item isolation
                timings_ms = merge_timings(
                    result.timings_ms, write_ms=elapsed_ms_since(write_started)
                )
                record_timing_totals(timing_totals_ms, timing_item_counts, timings_ms)
                print(
                    f"[{result.index}/{total}] failed\t{result.item.id}\t"
                    f"{redact(str(exc))}"
                )
                run_log.write(
                    "item_failed",
                    item=item_log_record(result.item, index=result.index, total=total),
                    error=redact(str(exc)),
                    model_endpoint=result.model_endpoint,
                    attempts=result.attempts,
                    timings_ms=timings_ms,
                    source_strategy=result.source_strategy,
                    elapsed_ms=result.elapsed_ms,
                )
                if args.fail_fast:
                    raise
                return 0, 1
            timings_ms = merge_timings(
                result.timings_ms, write_ms=elapsed_ms_since(write_started)
            )
            record_timing_totals(timing_totals_ms, timing_item_counts, timings_ms)
            run_log.write(
                "item_written",
                item=item_log_record(result.item, index=result.index, total=total),
                tags=result.tags,
                annotation_chars=len(result.annotation),
            )
        else:
            timings_ms = merge_timings(result.timings_ms)
            record_timing_totals(timing_totals_ms, timing_item_counts, timings_ms)

        endpoint = model_endpoint_record_summary(result.model_endpoint)
        print(
            f"[{result.index}/{total}] {action}\t{result.item.id}\t"
            f"{result.item.name}\t{len(result.tags)} tags\t{endpoint}"
        )
        run_log.write(
            "item_completed",
            item=item_log_record(result.item, index=result.index, total=total),
            action=action,
            changed=True,
            tags=result.tags,
            tag_count=len(result.tags),
            model_endpoint=result.model_endpoint,
            attempts=result.attempts,
            timings_ms=timings_ms,
            source_strategy=result.source_strategy,
            elapsed_ms=result.elapsed_ms,
        )
        return 1, 0

    work_items: list[tuple[int, EagleItem]] = []
    skipped_reasons: dict[int, str] = {}
    for index, item in enumerate(items, start=1):
        if has_moodboard_notes(item.annotation) and not args.force:
            skipped_reasons[index] = "already processed"
        elif reason := unsupported_media_reason(item):
            skipped_reasons[index] = reason
        else:
            work_items.append((index, item))

    probe_result: TagItemResult | None = None
    if work_items:
        probe_index, probe_item = work_items[0]
        probe_result = analyze_tag_item(
            index=probe_index,
            item=probe_item,
            eagle=eagle,
            vision=vision,
            image_root=image_root,
            taxonomy=taxonomy,
            image_edge=args.image_edge,
            retries=args.retries,
            max_tags=args.max_tags,
        )

    def emit_skip(index: int, item: EagleItem, reason: str) -> None:
        nonlocal skipped
        skipped += 1
        print(f"[{index}/{total}] skip\t{item.id}\t{item.name}\t{reason}")
        run_log.write(
            "item_skipped",
            item=item_log_record(item, index=index, total=total),
            reason=reason,
        )

    def finish_run(*, aborted: bool = False) -> int:
        if not args.write:
            print("Dry run only. Re-run with --write to update Eagle.")
        print(f"Board: {board.path} ({board.id})")
        print_scope_summary(scope)
        print(f"Changed: {changed}")
        print(f"Skipped: {skipped}")
        print(f"Failed: {failed}")
        run_log.write(
            "run_complete",
            board={"id": board.id, "path": board.path, "name": board.name},
            changed=changed,
            skipped=skipped,
            failed=failed,
            aborted=aborted,
            timing_totals_ms=timing_totals_ms,
            timing_item_counts=timing_item_counts,
        )
        return 0 if failed == 0 else 1

    if probe_result is not None and isinstance(
        probe_result.error, ProviderAuthenticationError
    ):
        for index, item in enumerate(items, start=1):
            if reason := skipped_reasons.get(index):
                emit_skip(index, item, reason)
                continue
            if index == probe_result.index:
                result_changed, result_failed = handle_result(probe_result)
                changed += result_changed
                failed += result_failed
                run_log.write(
                    "run_aborted",
                    reason=redact(str(probe_result.error)),
                    attempts=probe_result.attempts,
                )
                return finish_run(aborted=True)

    remaining_work_items = work_items[1:] if probe_result is not None else []
    results = run_tag_analysis(
        work_items=remaining_work_items,
        eagle=eagle,
        vision=vision,
        vision_factory=(
            lambda: (
                public_attr("make_vision_client")(args)
                if args.concurrency > 1
                else None
            )
        ),
        image_root=image_root,
        taxonomy=taxonomy,
        image_edge=args.image_edge,
        retries=args.retries,
        max_tags=args.max_tags,
        concurrency=args.concurrency,
    )
    result_iter = iter(results)
    for index, item in enumerate(items, start=1):
        if reason := skipped_reasons.get(index):
            emit_skip(index, item, reason)
            continue
        result = (
            probe_result
            if probe_result is not None and index == probe_result.index
            else next(result_iter)
        )
        result_changed, result_failed = handle_result(result)
        changed += result_changed
        failed += result_failed
        if isinstance(result.error, ProviderAuthenticationError):
            run_log.write(
                "run_aborted",
                reason=redact(str(result.error)),
                attempts=result.attempts,
            )
            return finish_run(aborted=True)

    return finish_run()


def _emit_final_result(
    printer: Printer, args: argparse.Namespace, result: RunResult
) -> int:
    if getattr(args, "json", False):
        print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
    elif not getattr(args, "quiet", 0):
        action = (
            tr("updated", "已更新")
            if getattr(args, "write", False)
            else tr("analyzed (dry run)", "已分析（试运行）")
        )
        if result.cancelled:
            printer.emit(tr("Cancelled", "已取消"), state="warning", force=True)
        else:
            printer.emit(tr("Complete", "处理完成"), tone="primary", force=True)
        printer.emit("")
        printer.emit(
            tr(f"{result.changed} {action}", f"{result.changed} 项{action}"),
            state="success",
            force=True,
        )
        printer.emit(
            tr(f"{result.skipped} skipped", f"跳过 {result.skipped} 项"),
            state="warning",
            force=True,
        )
        printer.emit(
            tr(f"{result.failed} failed", f"失败 {result.failed} 项"),
            state="failure",
            force=True,
        )
        if not result.cancelled:
            printer.emit("")
            printer.emit(
                tr("Use -v for image results", "使用 -v 查看逐张图片结果"),
                state="next",
                force=True,
            )
    elif not result.cancelled:
        action = (
            tr("updated", "已更新")
            if getattr(args, "write", False)
            else tr("analyzed (dry run)", "已分析（试运行）")
        )
        printer.emit(
            tr(
                f"Complete: {result.changed} {action}, {result.failed} failed",
                f"处理完成：{result.changed} 项{action}，失败 {result.failed} 项",
            ),
            force=True,
        )
    return result.exit_code


def _command_guided_tag_v2(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    printer = Printer(plain=getattr(args, "plain", False))
    eagle = public_attr("EagleClient")(args.eagle_api)
    try:
        eagle.app_info()
    except CoreError:
        # Board discovery remains the source of truth for guided mode.  Some
        # compatible Eagle implementations do not expose application info;
        # do not make that optional probe block an otherwise valid run.
        pass
    try:
        if getattr(args, "selected", False) or getattr(args, "library", False):
            resolved = resolve_item_scope(
                eagle,
                ScopeInput(
                    folder=args.board,
                    selected=getattr(args, "selected", False),
                    library=getattr(args, "library", False),
                    tags=tuple(getattr(args, "tags", []) or []),
                    recursive=not args.no_recursive,
                    max_items=args.max_board_items,
                    rating=getattr(args, "rating", None),
                    shape=getattr(args, "shape", "") or "",
                ),
            )
            scope = BoardScope(
                Board(
                    "selected" if args.selected else "library",
                    "Current selection" if args.selected else "Entire library",
                    "Current selection" if args.selected else resolved.source,
                ),
                [],
                resolved.items,
            )
        else:
            scope = _load_guided_board_scope(args, eagle, printer)
            if scope is None:
                printer.emit(
                    tr("Cancelled. Nothing changed.", "已取消，没有更改。"),
                    state="warning",
                )
                return 3 if getattr(args, "_interactive_home", False) else 0
    except MoodtagError as exc:
        if getattr(args, "library", False) and "exceeding --max-board-items" in str(
            exc
        ):
            printer.emit(
                tr(
                    str(exc),
                    f"图库项目数超过上限：{exc}。请缩小范围或调整 --max-board-items。",
                ),
                state="warning",
            )
            return 4 if getattr(args, "_interactive_home", False) else 2
        raise
    items = scope.items
    completed = sum(has_moodboard_notes(item.annotation) for item in items)
    malformed = sum(analysis_item_status(item) == "malformed" for item in items)
    unsupported = sum(unsupported_media_reason(item) is not None for item in items)
    pending = sum(
        analysis_item_status(item) == "missing"
        and unsupported_media_reason(item) is None
        for item in items
    )
    if not items:
        printer.emit(tr("No matching images.", "没有找到匹配的图片。"), state="warning")
        return 3 if getattr(args, "_interactive_home", False) else 0
    printer.emit(tr("Scope ready", "扫描完成"), state="next")
    scope_label = (
        tr("Library", "图库")
        if getattr(args, "library", False)
        else tr("Scope", "范围")
    )
    printer.emit(f"{scope_label}: {scope.board.path}")
    filter_parts = []
    if args.tags:
        filter_parts.append(tr("Tags: ", "标签：") + ", ".join(args.tags))
    if getattr(args, "rating", None) is not None:
        filter_parts.append(
            tr(f"Rating: {args.rating} (exact)", f"评分：{args.rating}（精确）")
        )
    if getattr(args, "shape", None):
        filter_parts.append(tr(f"Shape: {args.shape}", f"形状：{args.shape}"))
    if filter_parts:
        printer.emit(tr("Filters: ", "筛选：") + " · ".join(filter_parts))
    printer.emit(
        tr(
            f"{len(items)} images · {completed} analyzed · {pending} pending",
            f"{len(items)} 张图片 · 已分析 {completed} · 待处理 {pending}",
        )
    )
    if unsupported or malformed:
        printer.emit(
            tr(
                f"{unsupported} unsupported · {malformed} malformed descriptions",
                f"不支持 {unsupported} · 异常描述 {malformed}",
            ),
            state="warning",
        )
    if pending == 0 and malformed == 0 and completed == 0:
        printer.emit(
            tr("No supported images to analyze.", "没有可分析的受支持图片。"),
            state="warning",
        )
        return 0
    eligible = len(items) - unsupported
    if pending == eligible and eligible > 0:
        selected = 0
    elif pending == 0 and completed > 0 and malformed == 0:
        try:
            selected = choose(
                printer,
                tr("All images are already analyzed", "所有图片都已分析"),
                [
                    MenuChoice(
                        tr(
                            f"Regenerate all ({len(items)})",
                            f"全部重新生成（{len(items)}）",
                        ),
                        primary=True,
                    )
                ],
                allow_back=True,
            )
        except MenuCancelled:
            return 0
        if selected is None:
            return 3 if getattr(args, "_interactive_home", False) else 0
        selected = 1
    elif pending == 0 and completed == 0 and malformed > 0:
        try:
            choice = choose(
                printer,
                tr(
                    f"{malformed} malformed descriptions found",
                    f"发现 {malformed} 条异常描述",
                ),
                [
                    MenuChoice(
                        tr(
                            f"Regenerate malformed images ({malformed})",
                            f"重新生成异常图片（{malformed}）",
                        ),
                        primary=True,
                    )
                ],
                allow_back=True,
            )
        except MenuCancelled:
            return 0
        if choice is None:
            return 3 if getattr(args, "_interactive_home", False) else 0
        selected = 1
    else:
        try:
            selected = choose(
                printer,
                tr("How should we proceed?", "如何处理？"),
                [
                    MenuChoice(
                        tr(
                            f"Analyze pending images ({pending})",
                            f"分析待处理图片（{pending}）",
                        ),
                        primary=True,
                    ),
                    MenuChoice(
                        tr(
                            f"Regenerate all ({len(items)})",
                            f"全部重新生成（{len(items)}）",
                        )
                    ),
                ],
                allow_back=True,
            )
        except MenuCancelled:
            printer.emit(
                tr("Cancelled. Nothing changed.", "已取消，没有更改。"),
                state="warning",
            )
            return 0
        if selected is None:
            return 3 if getattr(args, "_interactive_home", False) else 0

    if not getattr(args, "mock_model", False):
        while True:
            try:
                ensure_model_setup(args)
                break
            except SetupCancelled:
                if not sys.stdin.isatty():
                    return 2
                printer.emit(
                    tr(
                        "Model setup cancelled. Your image scope is still selected.",
                        "模型设置已取消，当前图片范围仍然保留。",
                    ),
                    state="warning",
                )
                retry = choose(
                    printer,
                    tr("Continue this task", "继续当前任务"),
                    [
                        tr("Retry model setup", "重试模型设置"),
                        tr("Change model", "切换模型"),
                        tr("Cancel this task", "取消当前任务"),
                    ],
                    default=0,
                )
                if retry == 0:
                    continue
                if retry == 1:
                    values = _setup_prompt(printer, load_user_config())
                    _persist_setup(values)
                    args.base_url = values["base_url"]
                    args.model = values["model"]
                    args.source = values.get("source", "openai-compatible")
                    args.ollama_preset = values.get("ollama_preset", "qwen-instruct")
                    if values.get("api_key"):
                        os.environ["MOODTAG_API_KEY"] = values["api_key"]
                    continue
                return 0
            except MoodtagError as exc:
                if not sys.stdin.isatty():
                    raise
                printer.emit(
                    tr(f"Model setup issue: {exc}", f"模型设置遇到问题：{exc}"),
                    state="warning",
                )
                retry = choose(
                    printer,
                    tr("Model setup", "模型设置"),
                    [
                        tr("Retry", "重试"),
                        tr("Change model", "切换模型"),
                        tr("Cancel this task", "取消当前任务"),
                    ],
                    default=0,
                )
                if retry == 0:
                    continue
                if retry == 1:
                    values = _setup_prompt(printer, load_user_config())
                    _persist_setup(values)
                    args.base_url = values["base_url"]
                    args.model = values["model"]
                    args.source = values.get("source", "openai-compatible")
                    args.ollama_preset = values.get("ollama_preset", "qwen-instruct")
                    if values.get("api_key"):
                        os.environ["MOODTAG_API_KEY"] = values["api_key"]
                    continue
                return 0
    model_name = str(getattr(args, "model", "") or "configured model")
    model_source = str(getattr(args, "source", "") or "model provider")
    if model_source == "openai-compatible":
        model_source = "Remote API"
    count = pending if selected == 0 else len(items)
    printer.emit(tr(f"Ready to analyze {count} images", f"准备分析 {count} 张图片"))
    printer.emit(f"{tr('Model', '模型')}   {model_name} · {model_source}")
    printer.emit(f"{tr('Style', '风格')}   {tagging_style_name(args.profile)}")
    start_default = selected == 0
    prompt = (
        tr("Regenerate all images?", "重新生成全部图片？")
        if selected == 1
        else tr("Start tagging?", "开始标注？")
    )
    if not prompt_yes_no(prompt, default=start_default, printer=printer):
        printer.emit(
            tr("Cancelled. Nothing changed.", "已取消，没有更改。"),
            state="warning",
        )
        return 0
    args.guided_main_flow = False
    args.write = True
    args.force = selected == 1
    args._resolved_scope = scope
    return _command_tag_v2(args)


def _load_guided_board_scope(
    args: argparse.Namespace, eagle: Any, printer: Printer
) -> BoardScope | None:
    """Resolve an interactive board query, letting the user recover from ambiguity."""
    while True:
        try:
            with spinner(
                printer,
                tr("Scanning Eagle folder…", "正在扫描 Eagle 文件夹…"),
            ):
                return load_board_scope(
                    eagle,
                    args.board,
                    recursive=not args.no_recursive,
                    max_board_items=args.max_board_items,
                )
        except MoodtagError as exc:
            candidates = find_board_candidates(
                normalize_board_query(args.board), eagle.boards()
            )
            if not candidates:
                printer.emit(
                    tr(f"Could not find that folder: {exc}", f"找不到该文件夹：{exc}"),
                    state="warning",
                )
                printer.emit(
                    tr(
                        "Folder URL, ID, name, or path · b Back · q Quit",
                        "输入文件夹 URL、ID、名称或路径 · b 返回 · q 退出",
                    )
                )
                try:
                    value = input().strip()
                except (EOFError, KeyboardInterrupt):
                    return None
                if value.lower() == "q":
                    return None
                if value.lower() == "b" or not value:
                    return None
                args.board = value
                continue
            if len(candidates) == 1:
                args.board = candidates[0].id
                continue
        try:
            selected = choose(
                printer,
                tr("Multiple folders found", "找到多个文件夹"),
                [f"{board.path} ({board.id})" for board in candidates],
                allow_back=True,
            )
        except MenuCancelled:
            return None
        if selected is None:
            return None
        if selected is None:
            printer.emit("Folder URL, ID, name, or path:", state="next")
            try:
                args.board = input().strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if not args.board:
                return None
            continue
        args.board = candidates[selected].id


def _command_tag_v2(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    printer = Printer(
        plain=getattr(args, "plain", False) or getattr(args, "json", False),
        quiet=getattr(args, "quiet", 0),
    )
    session = Session(printer)
    try:
        with session.wait("Connecting to Eagle and resolving scope"):
            eagle = public_attr("EagleClient")(args.eagle_api)
            try:
                eagle.app_info()
            except CoreError:
                # Application metadata is advisory; board/item APIs are enough
                # to run the tagging command and are easier to mock in CI.
                pass
            scope = getattr(args, "_resolved_scope", None)
            if scope is None:
                resolved = resolve_item_scope(
                    eagle,
                    ScopeInput(
                        folder=args.board,
                        selected=getattr(args, "selected", False),
                        library=getattr(args, "library", False),
                        tags=tuple(getattr(args, "tags", []) or []),
                        recursive=not args.no_recursive,
                        max_items=args.max_board_items,
                        rating=getattr(args, "rating", None),
                        shape=getattr(args, "shape", "") or "",
                    ),
                )
                title = (
                    "Current selection"
                    if args.selected
                    else "Entire library"
                    if args.library
                    else args.board
                )
                scope = BoardScope(
                    board=Board(
                        id="selected"
                        if args.selected
                        else "library"
                        if args.library
                        else args.board,
                        name=title,
                        path="Current selection" if args.selected else resolved.source,
                    ),
                    folders=[],
                    items=resolved.items,
                )
        if not scope.items:
            return _emit_final_result(
                printer,
                args,
                RunResult(scope.board.path or "selected", 0, 0, 0, 0, 0),
            )
        vision = public_attr("make_vision_client")(args)
        if isinstance(vision, OllamaVisionClient):
            vision.preflight()
    except CoreError as exc:
        raise MoodtagError(str(exc)) from exc

    items = scope.items
    if args.limit:
        pending = [
            item
            for item in items
            if not has_moodboard_notes(item.annotation) or args.force
        ]
        processed = [item for item in items if item not in pending]
        items = pending[: args.limit] + processed
    total = len(items)
    work_items: list[tuple[int, EagleItem]] = []
    skipped = 0
    for index, item in enumerate(items, 1):
        status = analysis_item_status(item)
        is_valid = has_moodboard_notes(item.annotation)
        if is_valid and not args.force:
            skipped += 1
            if getattr(args, "verbose", 0) and not getattr(args, "quiet", 0):
                printer.emit(f"Skip {item.name}: already tagged", state="warning")
        elif status == "malformed":
            skipped += 1
            if not getattr(args, "quiet", 0):
                printer.emit(
                    f"Skip {item.name}: malformed Moodtag annotation", state="warning"
                )
        elif unsupported_media_reason(item):
            skipped += 1
            if getattr(args, "verbose", 0) and not getattr(args, "quiet", 0):
                printer.emit(
                    f"Skip {item.name}: unsupported file type", state="warning"
                )
        else:
            work_items.append((index, item))
    if not getattr(args, "quiet", 0):
        printer.emit(
            tr(
                f"Ready to scan ‘{scope.board.path}’: {len(work_items)} of {total} images to analyze",
                f"扫描准备就绪：‘{scope.board.path}’ 中有 {total} 张图片，待分析 {len(work_items)} 张",
            ),
            state="active",
        )
    endpoint_record = model_endpoint_record(vision)
    if endpoint_record:
        printer.emit(
            f"Image destination: {image_destination_message(endpoint_record)}",
            force=True,
        )

    taxonomy = load_profile_taxonomy(args.profile)
    image_root = eagle_library_images_root(eagle)
    analyzed: list[TagItemResult] = []
    failed = 0
    cancelled = False
    try:
        if work_items:
            probe_index, probe_item = work_items[0]
            with session.wait(tr("Checking first image", "正在检查首张图片")):
                probe = analyze_tag_item(
                    index=probe_index,
                    item=probe_item,
                    eagle=eagle,
                    vision=vision,
                    image_root=image_root,
                    taxonomy=taxonomy,
                    image_edge=args.image_edge,
                    retries=args.retries,
                    max_tags=args.max_tags,
                )
            if probe.error:
                error = redact(str(probe.error))
                printer.error(f"Model check failed: {error}")
                return _emit_final_result(
                    printer,
                    args,
                    RunResult(
                        scope.board.path,
                        total,
                        len(work_items),
                        0,
                        skipped,
                        1,
                        error=error,
                    ),
                )
            remainder = work_items[1:]
            analyzed.append(probe)
            with session.progress(
                len(work_items), tr("Analyzing", "正在分析")
            ) as progress:
                progress.update(f"{probe.item.name}: ✓")
                for result in run_tag_analysis(
                    work_items=remainder,
                    eagle=eagle,
                    vision=vision,
                    vision_factory=(lambda: public_attr("make_vision_client")(args))
                    if args.concurrency > 1
                    else None,
                    image_root=image_root,
                    taxonomy=taxonomy,
                    image_edge=args.image_edge,
                    retries=args.retries,
                    max_tags=args.max_tags,
                    concurrency=args.concurrency,
                ):
                    analyzed.append(result)
                    outcome = f"{result.item.name}: {'×' if result.error else '✓'}"
                    progress.update(outcome)
                    if result.error:
                        failed += 1
                    if getattr(args, "verbose", 0) and not getattr(args, "quiet", 0):
                        printer.emit(
                            outcome, state="failure" if result.error else "success"
                        )
                    if getattr(args, "verbose", 0) >= 2 and not getattr(
                        args, "quiet", 0
                    ):
                        printer.emit(
                            f"{model_endpoint_record_summary(result.model_endpoint)} "
                            f"attempts={len(result.attempts)} elapsed_ms={result.elapsed_ms}"
                        )
    except KeyboardInterrupt:
        cancelled = True
        printer.emit(
            "Stopping. Unprocessed images will not be updated.", state="warning"
        )

    changed = 0
    if not cancelled and args.write:
        successes = sorted(
            (result for result in analyzed if result.error is None),
            key=lambda result: result.index,
        )
        with session.progress(
            len(successes), tr("Updating Eagle", "正在更新 Eagle")
        ) as progress:
            try:
                for result in successes:
                    try:
                        write_status = write_analysis_result(
                            eagle, result, skip_existing=not args.force
                        )
                        if write_status == "skipped":
                            progress.update(f"{result.item.name}: skipped")
                            continue
                    except KeyboardInterrupt:
                        cancelled = True
                        printer.emit(
                            "Stopping. Some images may already be updated.",
                            state="warning",
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        progress.update(f"{result.item.name}: ×")
                        printer.emit(
                            f"Update failed: {redact(str(exc))}", state="failure"
                        )
                    else:
                        changed += 1
                        progress.update(f"{result.item.name}: ✓")
            except KeyboardInterrupt:
                cancelled = True
    elif not args.write and not getattr(args, "quiet", 0):
        printer.emit(
            tr(
                "Analysis complete. Eagle was not updated (dry run).",
                "分析完成。试运行模式未修改 Eagle。",
            ),
            state="warning",
        )
    result = RunResult(
        scope.board.path,
        total,
        len(work_items),
        changed if args.write else len([item for item in analyzed if not item.error]),
        skipped,
        failed,
        cancelled,
    )
    return _emit_final_result(printer, args, result)


def command_brief(args: argparse.Namespace) -> int:
    validate_board_scope_args(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    markdown = build_brief(board, items)
    if args.output:
        output = Path(args.output)
        if output.is_dir():
            output = output / "moodboard-brief.md"
        output.write_text(markdown, encoding="utf-8")
        Printer().emit(f"Wrote {output}", state="success")
    else:
        print(markdown, end="")
    return 0


def build_brief(board: Board, items: list[EagleItem]) -> str:
    tag_counts: dict[str, int] = {}
    for item in items:
        for tag in item.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    common = sorted(tag_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20]
    lines = [
        f"# Moodboard Brief: {board.path}",
        "",
        f"- Board ID: {board.id}",
        f"- Items: {len(items)}",
        "- Common tags: " + ", ".join(f"{tag} ({count})" for tag, count in common),
        "",
        "| # | Eagle ID | Name | Tags | Brief |",
        "|---|---|---|---|---|",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    escape_md(item.id),
                    escape_md(item.name),
                    escape_md(", ".join(item.tags)),
                    escape_md(extract_notes_summary(item.annotation)),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def command_reset(args: argparse.Namespace) -> int:
    validate_board_scope_args(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    scope = load_board_scope(
        eagle,
        args.board,
        recursive=not args.no_recursive,
        max_board_items=args.max_board_items,
    )
    board = scope.board
    items = scope.items
    printer = Printer()
    changed = 0
    skipped = 0
    for item in items:
        if analysis_item_status(item) != "valid":
            if analysis_item_status(item) == "malformed":
                printer.emit(
                    f"skip\t{item.id}\t{item.name}\tmalformed Moodtag annotation"
                )
            continue
        changed += 1
        printer.emit(f"{'write' if args.write else 'dry-run'}\t{item.id}\t{item.name}")
        if args.write:
            item_info = getattr(eagle, "item_info", None)
            latest = item_info(item.id) if callable(item_info) else item
            if analysis_item_status(latest) != "valid":
                skipped += 1
                continue
            try:
                annotation = remove_notes_block(latest.annotation)
            except ValueError:
                skipped += 1
                continue
            eagle.update_item(item.id, annotation=annotation)
    if not args.write:
        printer.emit("Dry run only. Re-run with --write to remove Moodtag annotations.")
    printer.emit(f"Board: {board.path}")
    printer.emit(f"Reset candidates: {changed}")
    if skipped:
        printer.emit(f"Skipped: {skipped}")
    return 0


def effective_model_config(config: dict[str, str]) -> dict[str, str]:
    base_url = config.get("base_url", "")
    model = config.get("model", "")
    source = config.get("source") or ("openai-compatible" if base_url or model else "")
    if source == "ollama":
        return {
            "protocol": "ollama",
            "source": source,
            "base_url": base_url or "http://127.0.0.1:11434",
            "model": model,
        }
    protocol = ""
    if model:
        try:
            protocol = protocol_for_model(model)
        except CoreError:
            protocol = ""
    return {
        "protocol": protocol,
        "source": source,
        "base_url": base_url,
        "model": model,
    }


def _setup_prompt(
    printer: Printer, existing: dict[str, str] | None = None
) -> dict[str, str]:
    existing = existing or load_user_config()
    try:
        printer.emit(
            tr(
                "Remote API: no local model install; provider charges and remote image transfer may apply.",
                "远程 API：无需本地安装模型；服务商可能收费，图片会发送至远程服务。",
            )
        )
        printer.emit(
            tr(
                "Local Ollama: no remote model API charge; requires Ollama, a vision model, and local resources.",
                "本地 Ollama：不产生远程模型调用费用；需要安装 Ollama 和视觉模型，并使用本机资源。",
            )
        )
        protocol_index = choose(
            printer,
            tr("Choose model source", "选择模型来源"),
            [tr("Remote API", "远程 API"), tr("Ollama (local)", "Ollama（本地）")],
            default=0,
        )
        if protocol_index is None:
            raise SetupCancelled("Setup cancelled.")
        if protocol_index == 1:
            current_url = existing.get("base_url", "") or "http://127.0.0.1:11434"
            base_url = current_url
            probe = OllamaVisionClient(base_url=base_url, model="discovery")
            try:
                probe.preflight()
            except CoreError:
                printer.emit_hyperlink(
                    tr("Download Ollama ↗", "下载 Ollama ↗"),
                    "https://ollama.com/download/mac",
                )
                printer.emit(
                    tr(
                        f"Ollama URL [{current_url}]:",
                        f"Ollama 地址 [{current_url}]：",
                    )
                )
                base_url = input().strip() or current_url
                probe = OllamaVisionClient(base_url=base_url, model="discovery")
                probe.preflight()
            available = discover_ollama_vision_models(probe)
            if not available:
                raise SetupCancelled(
                    tr(
                        "No installed vision-capable Ollama models were found; install one explicitly.",
                        "没有找到已安装的 Ollama 视觉模型，请先安装兼容模型。",
                    )
                )
            if len(available) == 1:
                model_index = 0
            else:
                model_index = choose(
                    printer,
                    tr("Choose installed vision model", "选择已安装的视觉模型"),
                    available,
                )
                if model_index is None:
                    raise SetupCancelled("Setup cancelled.")
            return {
                "source": "ollama",
                "base_url": base_url,
                "model": available[model_index],
                "ollama_preset": "qwen-instruct",
                "api_key": "",
            }
        printer.emit(
            tr(
                "Remote API uses an endpoint, model, and API key; charges may apply.",
                "远程 API 需要服务地址、模型和 API Key，服务商可能收费。",
            )
        )
        printer.emit_hyperlink(
            tr("Get a Recommended API Service ↗", "注册推荐 API 服务 ↗"),
            "https://sub2.de5.net/register?aff=KBK7PER5ECUY",
        )
        models = load_model_catalog()
        model_index = choose(
            printer,
            tr("Choose Remote API model", "选择远程 API 模型"),
            [
                f"{entry.name} ({entry.id})"
                + (" · recommended" if entry.recommended else "")
                for entry in models
            ],
            allow_back=True,
        )
        if model_index is None:
            raise SetupCancelled("Setup cancelled.")
        model = models[model_index].id
        current_url = existing.get("base_url", "")
        printer.emit(
            tr(f"Service URL [{current_url}]:", f"服务地址 [{current_url}]：")
            if current_url
            else tr("Service URL:", "服务地址：")
        )
        base_url = input().strip() or current_url
        protocol = protocol_for_model(model)
    except (EOFError, KeyboardInterrupt, MenuCancelled, SetupCancelled) as exc:
        raise SetupCancelled("Setup cancelled.") from exc
    if not base_url or not model:
        raise MoodtagError("Setup cancelled.")
    base_url = normalize_base_url(base_url, protocol)
    try:
        printer.emit(
            tr(
                "API key (leave blank to keep current):",
                "API Key（留空则沿用当前 Key）：",
            )
        )
        api_key = getpass.getpass("").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise SetupCancelled("Setup cancelled.") from exc
    if not api_key:
        api_key = os.environ.get("MOODTAG_API_KEY", "").strip()
    if not api_key:
        raise SetupCancelled("Setup cancelled.")
    return {
        "source": "openai-compatible",
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def discover_ollama_vision_models(probe: OllamaVisionClient) -> list[str]:
    """Return installed models explicitly advertising vision capability."""
    available: list[str] = []
    for entry in probe.models():
        name = str(entry.get("name") or entry.get("model") or "")
        if not name:
            continue
        metadata = probe.inspect_model(name)
        capabilities = metadata.get("capabilities", entry.get("capabilities", []))
        if isinstance(capabilities, list) and "vision" in capabilities:
            available.append(name)
    return available


def _persist_setup(values: dict[str, str]) -> None:
    config_file = config_path()
    env_file = env_file_path()
    old_config = config_file.read_bytes() if config_file.exists() else None
    old_env = env_file.read_bytes() if env_file.exists() else None
    if not values.get("api_key"):
        saved_key = ""
        with contextlib.suppress(OSError):
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, separator, raw_value = line.partition("=")
                if separator and key.strip() == "MOODTAG_API_KEY":
                    saved_key = parse_env_value(raw_value)
                    break
        values = {
            **values,
            "api_key": os.environ.get("MOODTAG_API_KEY", "").strip() or saved_key,
        }
    try:
        config = load_user_config(config_file)
        profile_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "-",
            f"{values.get('source', 'openai-compatible')}-{values.get('model', 'model')}",
        ).strip("-")
        try:
            profiles = json.loads(config.get(NAMED_PROFILES_KEY, "{}"))
        except json.JSONDecodeError:
            profiles = {}
        if not isinstance(profiles, dict):
            profiles = {}
        profiles[profile_id] = {
            key: values[key]
            for key in ("source", "base_url", "model", "ollama_preset")
            if key in values
        }
        config[NAMED_PROFILES_KEY] = json.dumps(profiles, ensure_ascii=False)
        config[ACTIVE_PROFILE_KEY] = profile_id
        config.update(profiles[profile_id])
        save_user_config(config, config_file)
        if values.get("api_key"):
            save_env_values({"MOODTAG_API_KEY": values["api_key"]}, env_file)
    except Exception:
        if old_config is None:
            with contextlib.suppress(FileNotFoundError):
                config_file.unlink()
        else:
            config_file.write_bytes(old_config)
        if old_env is None:
            with contextlib.suppress(FileNotFoundError):
                env_file.unlink()
        else:
            env_file.write_bytes(old_env)
        raise


def command_config_model(args: argparse.Namespace) -> int:
    profile_id = str(getattr(args, "profile_id", "") or "").strip()
    if profile_id:
        config = load_user_config()
        try:
            profiles = json.loads(config.get(NAMED_PROFILES_KEY, "{}"))
        except json.JSONDecodeError as exc:
            raise MoodtagError("Named model profiles are invalid.") from exc
        if profile_id not in profiles:
            raise MoodtagError(f"Unknown model profile: {profile_id}")
        config.update(profiles[profile_id])
        config[ACTIVE_PROFILE_KEY] = profile_id
        save_user_config(config)
        Printer().emit(f"Active model profile: {profile_id}", state="success")
        return 0
    if not sys.stdin.isatty():
        raise MoodtagError("Interactive model setup requires a TTY.")
    printer = Printer()
    try:
        values = _setup_prompt(printer, load_user_config())
    except SetupCancelled:
        printer.emit("Model setup cancelled. Nothing changed.", state="warning")
        return 0
    source = values.get("source", "openai-compatible")
    printer.emit(
        f"API format: {source if source == 'ollama' else protocol_for_model(values['model'])}"
    )
    printer.emit(f"Service URL: {values['base_url']}")
    printer.emit(f"Model: {values['model']}")
    printer.emit("API key: Not required" if source == "ollama" else "API key: Ready")
    _persist_setup(values)
    printer.emit("Model setup saved.", state="success")
    return 0


def command_config_profile(args: argparse.Namespace) -> int:
    profiles = ["editorial", "default"]
    profile = str(getattr(args, "profile", "") or "").strip()
    if not profile:
        if not sys.stdin.isatty():
            raise MoodtagError("Pass a tagging style name in non-interactive mode.")
        current = load_user_config().get("profile", DEFAULT_PROFILE) or DEFAULT_PROFILE
        try:
            selected = choose(
                Printer(),
                tr(
                    f"Choose tagging style (current: {tagging_style_name(current)})",
                    f"选择标注风格（当前：{tagging_style_name(current)}）",
                ),
                [
                    tr(
                        tagging_style_name(value),
                        "通用" if value == "default" else "Editorial",
                    )
                    for value in profiles
                ],
            )
        except MenuCancelled:
            return 0
        if selected is None:
            return 0
        profile = profiles[selected]
    try:
        profile = resolve_profile(profile).id
    except CoreError as exc:
        raise MoodtagError(
            f"Unknown tagging style: {profile}. "
            f"Available styles: {', '.join(tagging_style_name(item) for item in profiles)}"
        ) from exc
    update_user_config({"profile": profile})
    Printer().emit(
        f"Tagging style saved: {tagging_style_name(profile)}", state="success"
    )
    return 0


def command_config_show(args: argparse.Namespace) -> int:
    config = load_user_config()
    model_config = effective_model_config(config)
    eagle_api = config.get("eagle_api", DEFAULT_EAGLE_API)
    view = public_config_view(
        config,
        api_key_set=bool(os.environ.get("MOODTAG_API_KEY", "").strip()),
    )
    view = {
        **view,
        "protocol": model_config["protocol"],
        "base_url": model_config["base_url"],
        "model": model_config["model"],
        "eagle_api": eagle_api,
        "env_file": str(env_file_path()),
    }
    if args.json:
        print(json.dumps(view, ensure_ascii=False, sort_keys=True))
        return 0
    printer = Printer()
    printer.emit(
        "Model configuration: "
        + (
            "Ready"
            if view["base_url"]
            and view["model"]
            and (view["source"] == "ollama" or view["api_key"] == "set")
            else "Needs setup"
        )
    )
    printer.emit(f"Tagging style: {tagging_style_name(view['profile'])}")
    printer.emit(f"API format: {view['protocol'] or '-'}")
    printer.emit(f"Service URL: {view['base_url'] or '-'}")
    printer.emit(f"Model: {view['model'] or '-'}")
    if config.get(ACTIVE_PROFILE_KEY):
        printer.emit(f"Model profile: {config[ACTIVE_PROFILE_KEY]}")
    try:
        profiles = json.loads(config.get(NAMED_PROFILES_KEY, "{}"))
    except json.JSONDecodeError:
        profiles = {}
    if profiles:
        printer.emit("Available model profiles: " + ", ".join(sorted(profiles)))
    printer.emit(f"API key: {view['api_key_source']}")
    return 0


def command_config_reset(args: argparse.Namespace) -> int:
    del args
    if not sys.stdin.isatty():
        raise MoodtagError("Interactive reset requires a TTY.")
    printer = Printer()
    try:
        selected = choose(
            printer, "Reset settings", ["Tagging style", "Model setup", "Everything"]
        )
    except MenuCancelled:
        return 0
    if selected is None:
        return 0
    label = ("tagging style", "model setup", "everything")[selected]
    if not prompt_yes_no(f"Reset {label}?", default=False, printer=printer):
        return 0
    values = load_user_config()
    if selected in {0, 2}:
        values.pop("profile", None)
    if selected in {1, 2}:
        values.pop("base_url", None)
        values.pop("model", None)
        values.pop("source", None)
        values.pop("ollama_preset", None)
        values.pop(NAMED_PROFILES_KEY, None)
        values.pop(ACTIVE_PROFILE_KEY, None)
        remove_env_value("MOODTAG_API_KEY")
        os.environ.pop("MOODTAG_API_KEY", None)
    save_user_config(values)
    printer.emit("Settings reset.", state="success")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moodtag",
        usage=(
            "moodtag <board-url-or-id>\n"
            "       moodtag [--help|help]\n"
            "       moodtag config [profile|model|reset]\n"
            "       moodtag {status,tag,brief,export-context,reset,config} ..."
        ),
        description=(
            "Primary flow:\n"
            "  moodtag <board-url-or-id>\n\n"
            "What it does:\n"
            "  resolve board -> check setup -> show summary -> confirm -> write\n\n"
            "Support:\n"
            "  moodtag --help\n"
            "  moodtag config\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    user_config = load_user_config()

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--board",
            required=False,
            default="",
            help="Eagle folder URL or ID (name/path also accepted)",
        )
        p.add_argument(
            "--eagle-api",
            default=user_config.get("eagle_api", DEFAULT_EAGLE_API),
        )
        p.add_argument(
            "--max-board-items",
            type=int,
            default=env_int(
                "MOODTAG_MAX_BOARD_ITEMS", DEFAULT_MAX_BOARD_ITEMS, minimum=-1
            ),
            help=(
                "Abort when recursive board scope exceeds this many unique items "
                "(default: 9999; -1 disables)"
            ),
        )
        p.add_argument(
            "--no-recursive",
            action="store_true",
            help="Only use the selected Eagle folder, excluding child folders",
        )

    status = sub.add_parser("status", help="Show board tagging status")
    common(status)
    status.add_argument("--verbose", action="store_true")
    status.set_defaults(func=command_status)

    tag = sub.add_parser("tag", help="Analyze pending board items")
    common(tag)
    tag.add_argument(
        "--selected",
        action="store_true",
        help="Use Eagle's current selected items as a fixed scope snapshot",
    )
    tag.add_argument(
        "--library",
        action="store_true",
        help="Use the entire Eagle library as the scope",
    )
    tag.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Require an existing Eagle tag; repeat to require all tags",
    )
    tag.add_argument(
        "--rating",
        type=int,
        help="Filter by Eagle rating (0–5; exact match)",
    )
    tag.add_argument(
        "--shape",
        choices=EAGLE_SHAPES,
        help="Filter by Eagle-native image shape",
    )
    tag.add_argument("--write", action="store_true", help="Actually update Eagle")
    tag.add_argument("--force", action="store_true", help="Reprocess existing notes")
    tag.add_argument(
        "--profile",
        default=user_config.get("profile", DEFAULT_PROFILE) or DEFAULT_PROFILE,
        help="Tagging style to use (default: editorial)",
    )
    tag.add_argument(
        "--mock-model", action="store_true", help="Use deterministic mock model"
    )
    tag.set_defaults(
        base_url=user_config.get("base_url", ""),
        model=user_config.get("model", ""),
        source=user_config.get("source")
        or (
            "openai-compatible"
            if user_config.get("base_url") or user_config.get("model")
            else ""
        ),
        ollama_preset=user_config.get("ollama_preset", "qwen-instruct"),
    )
    tag.add_argument(
        "--image-edge",
        type=int,
        default=env_int("MOODTAG_IMAGE_EDGE", DEFAULT_IMAGE_EDGE, minimum=256),
    )
    tag.add_argument(
        "--concurrency",
        type=int,
        default=env_int(
            "MOODTAG_CONCURRENCY",
            1 if user_config.get("source") == "ollama" else DEFAULT_CONCURRENCY,
            minimum=1,
        ),
        help="Number of image analysis requests to run in parallel",
    )
    tag.add_argument(
        "--max-tags",
        type=int,
        default=env_int("MOODTAG_MAX_TAGS", DEFAULT_MAX_TAGS, minimum=1),
    )
    tag.add_argument("--limit", type=int, default=0)
    tag.add_argument(
        "--retries",
        type=int,
        default=env_int("MOODTAG_RETRIES", DEFAULT_RETRIES, minimum=0),
    )
    tag.add_argument(
        "--temperature",
        type=float,
        default=env_float("MOODTAG_TEMPERATURE", DEFAULT_TEMPERATURE, minimum=0),
    )
    tag.add_argument(
        "--top-p",
        type=float,
        default=env_float("MOODTAG_TOP_P", DEFAULT_TOP_P, minimum=0.000001, maximum=1),
    )
    tag.add_argument(
        "--max-tokens",
        type=int,
        default=env_int(
            "MOODTAG_MAX_TOKENS", DEFAULT_MAX_TOKENS, minimum=MIN_MAX_TOKENS
        ),
    )
    tag.add_argument("--fail-fast", action="store_true")
    tag.add_argument(
        "--json", action="store_true", help="Write one final JSON result to stdout"
    )
    tag.add_argument("--plain", action="store_true", help="Disable color and animation")
    tag.add_argument("-q", "--quiet", action="count", default=0)
    tag.add_argument("-v", "--verbose", action="count", default=0)
    tag.add_argument(
        "--no-response-format",
        action="store_true",
        default=env_bool("MOODTAG_NO_RESPONSE_FORMAT", DEFAULT_NO_RESPONSE_FORMAT),
    )
    tag.add_argument(
        "--response-format",
        dest="no_response_format",
        action="store_false",
        default=argparse.SUPPRESS,
    )
    tag.add_argument(
        "--guided-main-flow",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    tag.set_defaults(func=command_tag)

    brief = sub.add_parser("brief", help="Print a board brief from Eagle metadata")
    common(brief)
    brief.add_argument("--output", default="")
    brief.set_defaults(func=command_brief)

    export = sub.add_parser(
        "export-context", help="Export a board as compact Markdown context"
    )
    common(export)
    export.add_argument("--output", default="", help="Write Markdown to this file")
    export.add_argument(
        "--include-pending",
        action="store_true",
        help="Include items without complete Moodtag annotation",
    )
    export.set_defaults(func=command_export_context)

    reset = sub.add_parser(
        "reset", help="Remove moodtag annotation fields from board items"
    )
    common(reset)
    reset.add_argument("--write", action="store_true")
    reset.set_defaults(func=command_reset)

    config = sub.add_parser("config", help="View or change Moodtag configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_profile = config_sub.add_parser("profile", help="Select persisted profile")
    config_profile.add_argument("profile", nargs="?")
    config_profile.set_defaults(func=command_config_profile)
    config_model = config_sub.add_parser("model", help="Configure model service")
    config_model.add_argument(
        "profile_id", nargs="?", help="Switch to a saved model profile"
    )
    config_model.set_defaults(func=command_config_model)
    config_reset = config_sub.add_parser("reset", help="Safely reset configuration")
    config_reset.set_defaults(func=command_config_reset)
    config_show = config_sub.add_parser("show", help="Show configuration")
    config_show.add_argument("--json", action="store_true")
    config_show.set_defaults(func=command_config_show)
    return parser


def rewrite_main_argv(argv: list[str]) -> tuple[list[str], bool]:
    if not argv:
        return argv, False
    first = argv[0]
    if first == "config" and (len(argv) == 1 or argv[1].startswith("-")):
        return ["config", "show", *argv[1:]], False
    if first.startswith("-") or first in MAIN_FLOW_COMMANDS:
        return argv, False
    if is_board_candidate(first):
        return ["tag", "--board", first, "--guided-main-flow", *argv[1:]], True
    return argv, False


def is_board_candidate(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate or candidate.startswith("-") or candidate in MAIN_FLOW_COMMANDS:
        return False
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", candidate):
        return True
    if candidate.startswith(("eagle://", "http://", "https://", "/", "~")):
        return True
    return bool(re.fullmatch(r"[^\x00\r\n]+", candidate))


def clip_terminal_text(value: str, max_columns: int) -> str:
    columns = 0
    result: list[str] = []
    for char in value:
        width = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if columns + width > max_columns:
            result.append("…")
            break
        result.append(char)
        columns += width
    return "".join(result)


def command_home() -> int:
    printer = Printer()
    config = load_user_config()
    source = config.get("source") or (
        "openai-compatible" if config.get("base_url") or config.get("model") else ""
    )
    ready = bool(
        config.get("base_url")
        and config.get("model")
        and (source == "ollama" or os.environ.get("MOODTAG_API_KEY", "").strip())
    )
    configured = ready
    try:
        version = importlib.metadata.version("eagle-app-agent")
    except importlib.metadata.PackageNotFoundError:
        version = ""
    version_label = f"  v{version}" if version else ""
    printer.emit(f"◆  MOODTAG{version_label}", tone="brand")
    printer.emit(
        tr("AI image tagging for Eagle", "Eagle 智能图片标注工具"), tone="secondary"
    )
    printer.emit("")
    if configured:
        provider = "Ollama" if source == "ollama" else str(source or "Remote API")
        if provider == "openai-compatible":
            provider = "Remote API"
        printer.emit(
            f"{tr('Model', '模型')}   {clip_terminal_text(config.get('model', 'configured model'), 36)} · {provider}"
        )
    else:
        printer.emit(tr("Model   Not configured", "模型   尚未配置"), state="warning")
    current_style = config.get("profile", DEFAULT_PROFILE) or DEFAULT_PROFILE
    printer.emit_parts(
        [
            (f"{tr('Style', '风格')}   ", "secondary"),
            (tagging_style_name(current_style), "primary"),
        ]
    )
    printer.emit("")
    try:
        selected = choose(
            printer,
            tr("What would you like to do?", "接下来做什么？"),
            [
                MenuChoice(tr("Tag images", "标注图片"), primary=True),
                MenuChoice(
                    tr("Change style", "切换风格"),
                    section=tr("Settings", "设置"),
                ),
                MenuChoice(
                    tr("Change model", "切换模型")
                    if configured
                    else tr("Set up model", "配置模型")
                ),
            ],
            default=0,
        )
    except MenuCancelled:
        return 0
    if selected == 0:
        return command_guided_scope_flow(printer)
    if selected == 1:
        command_config_profile(argparse.Namespace(profile=""))
    else:
        command_config_model(argparse.Namespace())
    return command_home()


def command_guided_scope_flow(printer: Printer) -> int:
    """Collect scope-specific input while keeping Folder/Selection flows short."""
    while True:
        try:
            choice = choose(
                printer,
                tr("Where are the images?", "图片在哪里？"),
                [
                    tr("Eagle folder", "Eagle 文件夹"),
                    tr("Selected in Eagle", "Eagle 当前选中项"),
                    tr("Entire library", "整个图库"),
                ],
                allow_back=True,
            )
        except MenuCancelled:
            return 0
        if choice is None:
            return command_home()

        args = build_parser().parse_args(["tag"])
        args._interactive_home = True
        args.write = True
        if choice == 0:
            printer.emit(
                "Folder URL, ID, name, or path · b back · q quit", state="next"
            )
            try:
                printer.emit(">", tone="accent")
                folder = input().strip()
            except (EOFError, KeyboardInterrupt):
                return 0
            if folder.lower() == "q":
                return 0
            if folder.lower() == "b" or not folder:
                continue
            args.board = folder
        elif choice == 1:
            args.selected = True
        else:
            args.library = True
            try:
                filters = choose_filters(printer)
            except MenuCancelled:
                return 0
            if filters is None:
                continue
            args.tags, args.rating, args.shape = filters

        try:
            result = _command_guided_tag_v2(args)
        except MoodtagError as exc:
            printer.emit(str(exc), state="warning")
            return 2
        if result in {3, 4}:
            if result == 4:
                printer.emit(
                    "Add a filter to narrow the library scope.", state="warning"
                )
            continue
        return result


def choose_filters(
    printer: Printer,
) -> tuple[list[str], int | None, str] | None:
    """Ask for only the selected entire-library filter conditions."""
    while True:
        printer.emit("Entire library", state="next")
        printer.emit("Filters (optional)")
        printer.emit("1  Tags")
        printer.emit("2  Rating")
        printer.emit("3  Shape")
        printer.emit("Enter to skip · e.g. 1,2")
        try:
            printer.emit(">", tone="accent")
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise MenuCancelled from exc
        if answer == "q":
            raise MenuCancelled
        if answer == "b":
            return None
        if not answer:
            selected: set[int] = set()
            break
        try:
            selected = {int(value.strip()) for value in answer.split(",")}
        except ValueError:
            selected = set()
        if selected and selected <= {1, 2, 3}:
            break
        printer.emit(
            "Choose 1, 2, 3, or a comma-separated combination.", state="warning"
        )

    tags: list[str] = []
    rating: int | None = None
    shape = ""
    if 1 in selected:
        value = ask_scope_value(printer, "Tags (comma-separated; all must match)")
        if value is None:
            return None
        if value == "\x00":
            return choose_filters(printer)
        tags = [tag.strip() for tag in value.split(",") if tag.strip()]
        if not tags:
            printer.emit("Enter at least one tag.", state="warning")
            return choose_filters(printer)
    if 2 in selected:
        while True:
            value = ask_scope_value(printer, "Rating (0–5, exact match)")
            if value is None:
                return None
            if value == "\x00":
                return choose_filters(printer)
            try:
                rating = int(value)
            except ValueError:
                rating = -1
            if 0 <= rating <= 5:
                break
            printer.emit("Enter a rating from 0 to 5.", state="warning")
    if 3 in selected:
        choices = ", ".join(EAGLE_SHAPES)
        while True:
            value = ask_scope_value(printer, f"Shape ({choices})")
            if value is None:
                return None
            if value == "\x00":
                return choose_filters(printer)
            if value in EAGLE_SHAPES:
                shape = value
                break
            printer.emit("Enter one of the listed Eagle shapes.", state="warning")
    return tags, rating, shape


def ask_scope_value(printer: Printer, label: str) -> str | None:
    printer.emit(f"{label} · b back · q quit", state="next")
    try:
        printer.emit(">", tone="accent")
        value = input().strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise MenuCancelled from exc
    if value.lower() == "q":
        raise MenuCancelled
    if value.lower() == "b":
        return "\x00"
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        load_env_defaults()
        argv = list(sys.argv[1:] if argv is None else argv)
        if not argv:
            if sys.stdin.isatty() and sys.stdout.isatty():
                return command_home()
            raise MoodtagError(
                "Choose a scope explicitly: `moodtag <folder-url-or-id>`, "
                "`moodtag selected --write`, or `moodtag tag --library --write`. "
                "Use `moodtag --help` for filters and other commands."
            )
        for value in argv:
            if value == "--api-key" or value.startswith("--api-key="):
                raise MoodtagError(
                    "API keys must be entered through interactive setup or MOODTAG_API_KEY."
                )
        if argv and argv[0] == "help":
            build_parser().print_help()
            return 0
        if argv and argv[0] == "selected":
            argv = ["tag", "--selected", *argv[1:]]
        argv, _guided = rewrite_main_argv(argv)
        parser = build_parser()
        args = parser.parse_args(argv)
        return int(args.func(args) or 0)
    except MoodtagError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 2
    except CoreError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("× Stopped. Some images may already be updated.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
