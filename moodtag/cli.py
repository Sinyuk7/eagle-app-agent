#!/usr/bin/env python3
"""Moodtag: folder-first moodboard tagging for Eagle."""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time  # noqa: F401 - public compatibility for tests and external patching
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from moodtag_core.annotation import (
    ANNOTATION_LABEL_ORDER,
    build_annotation_block,
    extract_brief,
    has_analysis_annotation,
    parse_annotation_fields,
    remove_analysis_annotation,
    replace_analysis_annotation,
)
from moodtag_core.contract import (
    DEFAULT_BASE_URL,
    DEFAULT_FALLBACK_BASE_URL,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    MIN_MAX_TOKENS,
    CoreError,
    MoodtagAnalysis,
)
from moodtag_core.provider import (
    VisionClient as CoreVisionClient,
)
from moodtag_core.provider import (
    elapsed_ms_since,
)
from moodtag_core.response import normalize_analysis_json, parse_analysis_response

from .config import (
    ConfigError,
    load_user_config,
    public_config_view,
    update_user_config,
)

DEFAULT_EAGLE_API = "http://localhost:41595"
DEFAULT_IMAGE_EDGE = 1024
DEFAULT_MAX_TAGS = 15
DEFAULT_RETRIES = 2
DEFAULT_USER_AGENT = "moodtag/0.1"
DEFAULT_TAXONOMY = "default"
DEFAULT_LOG_KEEP = 50
LEGACY_DEFAULT_TAXONOMY_PATHS = {"taxonomy/default.json", "./taxonomy/default.json"}
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


class MoodtagError(CoreError):
    """Expected runtime error shown without traceback."""


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    path: str
    parent: str | None = None


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


def redact(text: str) -> str:
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", str(text))


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


def chat_completions_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise MoodtagError("Missing --base-url value")
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
        raise MoodtagError("Missing --base-url value")
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


def load_env_defaults() -> None:
    load_env_file(Path.cwd() / ".env")


def load_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise MoodtagError(f"Cannot read env file {path}: {exc}") from exc

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
        if key in os.environ:
            continue
        os.environ[key] = parse_env_value(raw_value)


def parse_env_value(raw_value: str) -> str:
    try:
        parts = shlex.split(raw_value, comments=True, posix=True)
    except ValueError as exc:
        raise MoodtagError(f"Invalid quoted env value: {exc}") from exc
    return " ".join(parts)


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
            "GET", url_join(self.base_url, "/api/v2/app/info"), timeout=5
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

        def visit(items: list[dict[str, Any]], prefix: str = "") -> None:
            for item in items:
                folder_id = str(item.get("id", "")).strip()
                name = str(item.get("name", "")).strip()
                if not folder_id or not name:
                    continue
                path = f"{prefix}/{name}" if prefix else name
                parent = item.get("parent")
                boards.append(Board(id=folder_id, name=name, path=path, parent=parent))
                children = item.get("children") or []
                if isinstance(children, list):
                    visit(children, path)

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

    def list_items(self, folder_id: str, *, limit: int = 10000) -> list[EagleItem]:
        # V2 POST supports folder filtering and returns total/offset metadata.
        data = http_request(
            "POST",
            url_join(self.base_url, "/api/v2/item/get"),
            json_body={"folders": [folder_id], "limit": limit, "offset": 0},
            timeout=30,
        )
        if isinstance(data, dict) and data.get("status") == "success":
            raw_items = data.get("data", {}).get("data", [])
            return [parse_item(raw) for raw in raw_items]

        # Fallback to the documented v1 list endpoint.
        query = urllib.parse.urlencode({"folders": folder_id, "limit": limit})
        data = http_request(
            "GET", url_join(self.base_url, f"/api/item/list?{query}"), timeout=30
        )
        self._expect_success(data, "item list")
        return [parse_item(raw) for raw in data.get("data", [])]

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

    def update_item(self, item_id: str, *, tags: list[str], annotation: str) -> None:
        data = http_request(
            "POST",
            url_join(self.base_url, "/api/item/update"),
            json_body={"id": item_id, "tags": tags, "annotation": annotation},
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
    )


def normalize_board_query(query: str) -> str:
    return query.strip().strip("/").replace("\\", "/")


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


def has_moodboard_notes(annotation: str) -> bool:
    return has_analysis_annotation(annotation)


def replace_notes_block(existing: str, block: str) -> str:
    return replace_analysis_annotation(existing, block)


def remove_notes_block(existing: str) -> str:
    return remove_analysis_annotation(existing)


def extract_notes_summary(annotation: str) -> str:
    return extract_brief(annotation)


def default_taxonomy_text() -> str:
    return (
        resources.files("moodtag_core.resources.taxonomy")
        .joinpath("default.json")
        .read_text(encoding="utf-8")
    )


def is_default_taxonomy_path(path: Path | str | None) -> bool:
    if path in {None, "", DEFAULT_TAXONOMY}:
        return True
    raw = str(path).replace("\\", "/")
    if raw == DEFAULT_TAXONOMY:
        return True
    return raw in LEGACY_DEFAULT_TAXONOMY_PATHS and not Path(path).exists()


def load_taxonomy(path: Path | str | None = DEFAULT_TAXONOMY) -> dict[str, list[str]]:
    try:
        if is_default_taxonomy_path(path):
            data = json.loads(default_taxonomy_text())
        else:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MoodtagError(f"Taxonomy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MoodtagError(f"Invalid taxonomy JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MoodtagError("Taxonomy must be a JSON object")
    taxonomy: dict[str, list[str]] = {}
    for group, tags in data.items():
        if not isinstance(tags, list):
            continue
        clean = [str(tag).strip() for tag in tags if str(tag).strip()]
        if clean:
            taxonomy[str(group)] = clean
    if not taxonomy:
        raise MoodtagError("Taxonomy has no usable tags")
    return taxonomy


def flatten_taxonomy(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for tags in taxonomy.values():
        for tag in tags:
            allowed[tag.lower()] = tag
    return allowed


def locate_original_from_thumbnail(thumbnail: Path, item: EagleItem) -> Path:
    return locate_original_in_info_dir(thumbnail.parent, item)


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
    def __init__(self, model: str = "mock-vision") -> None:
        self.model = model
        self.last_provider_name = "mock"
        self.last_provider_base_url = "mock://local"
        self.last_provider_model = model
        self.last_provider_attempts: list[Any] = []

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
                "brief": "模拟角色站在简洁背景前，身穿测试服并佩戴基础道具。",
                "elements": ["模拟角色", "测试服", "基础道具", "简洁背景", "中性配色"],
                "use": "主要用于 moodboard 自动标注流程参考，也可作为构图和光线描述测试。",
                "key": "画面信息稳定，便于确认标签和自然语言备注被正确拆分。",
                "camera": "中景平视构图，standard lens feel，主体居中且空间关系清晰。",
                "light_color": "soft directional light 为主，neutral tone，整体干净稳定。",
                "tags": first_tags,
                "use_intents": ["lighting_reference", "pose_reference"],
            },
            taxonomy=taxonomy,
            max_tags=max_tags,
        )
        self.last_provider_name = "mock"
        self.last_provider_base_url = "mock://local"
        self.last_provider_model = self.model
        self.last_provider_attempts = [
            {
                "name": "mock",
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


def build_prompt(taxonomy: dict[str, list[str]]) -> str:
    from moodtag_core.prompts import render_user_prompt

    return render_user_prompt(taxonomy)


def extract_chat_content_json(data: Any) -> dict[str, Any]:
    from moodtag_core.response import extract_assistant_content, parse_json_content

    return parse_json_content(extract_assistant_content(data))


def normalize_vl_result(
    data: Any,
    taxonomy: dict[str, list[str]] | None = None,
    max_tags: int = DEFAULT_MAX_TAGS,
) -> MoodtagAnalysis:
    taxonomy = taxonomy or load_taxonomy()
    try:
        if isinstance(data, str):
            return parse_analysis_response(
                {"choices": [{"message": {"content": data}}]},
                taxonomy=taxonomy,
                max_tags=max_tags,
            )
        if isinstance(data, dict) and "choices" in data:
            return parse_analysis_response(data, taxonomy=taxonomy, max_tags=max_tags)
        return normalize_analysis_json(data, taxonomy=taxonomy, max_tags=max_tags)
    except CoreError as exc:
        raise MoodtagError(str(exc)) from exc


def validate_vl_result(result: MoodtagAnalysis) -> None:
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
        raise MoodtagError("VL result missing required annotation fields")


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


def make_vision_client(args: argparse.Namespace) -> VisionClient | MockVisionClient:
    if getattr(args, "mock_vl", False):
        return MockVisionClient(args.model or "mock-vision")
    model = args.model or os.environ.get("MOODTAG_MODEL", "") or DEFAULT_MODEL
    if not model:
        raise MoodtagError("Missing model. Pass --model or set MOODTAG_MODEL.")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    fallback_api_key = os.environ.get("MOODTAG_API_KEY") or os.environ.get("VL_API_KEY")
    return VisionClient(
        base_url=args.base_url,
        fallback_base_url=args.fallback_base_url,
        model=model,
        fallback_model=args.fallback_model,
        api_key=api_key,
        fallback_api_key=fallback_api_key,
        response_format=not args.no_response_format,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
    )


def validate_tag_args(args: argparse.Namespace) -> None:
    if args.image_edge < 256:
        raise MoodtagError("--image-edge must be at least 256")
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


def command_status(args: argparse.Namespace) -> int:
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    items = eagle.list_items(board.id)
    processed = [item for item in items if has_moodboard_notes(item.annotation)]
    print(f"Board: {board.path} ({board.id})")
    print(f"Items: {len(items)}")
    print(f"Processed: {len(processed)}")
    print(f"Pending: {len(items) - len(processed)}")
    if args.verbose:
        for item in items:
            status = "processed" if has_moodboard_notes(item.annotation) else "pending"
            print(f"{status}\t{item.id}\t{item.name}")
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
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    items = eagle.list_items(board.id)
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
        print(f"Wrote {args.output}")
    else:
        print(markdown, end="")
    return 0


def format_provider_plan(vision: Any) -> str:
    records = provider_plan_records(vision)
    if not records:
        return "unavailable"
    return " -> ".join(
        (
            f"{record['name']}{provider_plan_status(record)}"
            f"({record['model']} @ {provider_display_host(record['base_url'])}, "
            f"key={record['api_key']})"
        )
        for record in records
    )


def provider_display_host(base_url: str) -> str:
    parts = urllib.parse.urlsplit(str(base_url or ""))
    if parts.netloc:
        return parts.netloc
    return str(base_url or "")


def provider_plan_status(record: dict[str, Any]) -> str:
    if record.get("active", True):
        return ""
    reason = record.get("skip_reason") or "inactive"
    return f"[skip:{reason}]"


def provider_plan_records(vision: Any) -> list[dict[str, Any]]:
    endpoints = getattr(vision, "endpoints", None)
    if callable(endpoints):
        active_keys = {
            (endpoint.name, endpoint.base_url, endpoint.model)
            for endpoint in endpoints(include_cooldown=True)
        }
        return [
            {
                "name": endpoint.name,
                "base_url": endpoint.base_url,
                "model": endpoint.model,
                "api_key": "set" if endpoint.api_key else "unset",
                "active": (endpoint.name, endpoint.base_url, endpoint.model)
                in active_keys,
                "skip_reason": "cooldown"
                if (endpoint.name, endpoint.base_url, endpoint.model) not in active_keys
                else "",
            }
            for endpoint in endpoints(include_cooldown=False)
        ]
    name = str(getattr(vision, "last_provider_name", "") or "mock")
    base_url = str(getattr(vision, "last_provider_base_url", "") or "mock://local")
    model = str(
        getattr(vision, "last_provider_model", "") or getattr(vision, "model", "")
    )
    return [
        {
            "name": name,
            "base_url": base_url,
            "model": model,
            "api_key": "set",
            "active": True,
            "skip_reason": "",
        }
    ]


def provider_summary(vision: Any) -> str:
    record = provider_record(vision)
    if not record:
        return "provider=unknown"
    return (
        f"provider={record['name']} model={record['model']} "
        f"host={provider_display_host(record['base_url'])}"
    )


def provider_record(vision: Any) -> dict[str, Any]:
    name = str(getattr(vision, "last_provider_name", "") or "")
    base_url = str(getattr(vision, "last_provider_base_url", "") or "")
    model = str(getattr(vision, "last_provider_model", "") or "")
    if not name and not base_url and not model:
        return {}
    return {"name": name, "base_url": base_url, "model": model}


def provider_attempt_records(vision: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for attempt in getattr(vision, "last_provider_attempts", []) or []:
        if isinstance(attempt, dict):
            records.append(
                {
                    "name": attempt.get("name", ""),
                    "base_url": attempt.get("base_url", ""),
                    "model": attempt.get("model", ""),
                    "ok": bool(attempt.get("ok")),
                    "elapsed_ms": attempt.get("elapsed_ms", 0),
                    "status": attempt.get("status"),
                    "error": redact(str(attempt.get("error", ""))),
                }
            )
            continue
        records.append(
            {
                "name": getattr(attempt, "name", ""),
                "base_url": getattr(attempt, "base_url", ""),
                "model": getattr(attempt, "model", ""),
                "ok": bool(getattr(attempt, "ok", False)),
                "elapsed_ms": getattr(attempt, "elapsed_ms", 0),
                "status": getattr(attempt, "status", None),
                "error": redact(str(getattr(attempt, "error", ""))),
            }
        )
    return records


def clear_provider_trace(vision: Any) -> None:
    for name, value in (
        ("last_provider_name", ""),
        ("last_provider_base_url", ""),
        ("last_provider_model", ""),
        ("last_provider_attempts", []),
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


def command_tag(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    taxonomy = load_taxonomy(Path(args.taxonomy))
    vision = public_attr("make_vision_client")(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
    run_log = make_tag_run_log()
    print(f"Log: {run_log.path}")
    print(f"Provider plan: {format_provider_plan(vision)}")
    run_log.write(
        "run_start",
        command="tag",
        mode="write" if args.write else "dry-run",
        board_query=args.board,
        limit=args.limit,
        force=args.force,
        image_edge=args.image_edge,
        max_tags=args.max_tags,
        retries=args.retries,
        provider_plan=provider_plan_records(vision),
    )
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    items = eagle.list_items(board.id)
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
    run_log.write(
        "board_loaded",
        board={"id": board.id, "path": board.path, "name": board.name},
        items=len(items),
    )

    for index, item in enumerate(items, start=1):
        if has_moodboard_notes(item.annotation) and not args.force:
            skipped += 1
            print(f"[{index}/{len(items)}] skip\t{item.id}\t{item.name}")
            run_log.write(
                "item_skipped",
                item=item_log_record(item, index=index, total=len(items)),
                reason="already processed",
            )
            continue
        item_started = time.monotonic()
        clear_provider_trace(vision)
        try:
            thumbnail = eagle.thumbnail_path(item.id)
            original = locate_original_from_thumbnail(thumbnail, item)
            with temporary_preview(original, image_edge=args.image_edge) as preview:
                result = vision.analyze(
                    preview.path,
                    taxonomy,
                    retries=args.retries,
                    max_tags=args.max_tags,
                )
            validate_vl_result(result)
            tags, _rejected = reconcile_tags(result, taxonomy, max_tags=args.max_tags)
            notes = build_notes_block(result)
            annotation = notes
            changed += 1
            action = "write" if args.write else "dry-run"
            provider = provider_summary(vision)
            print(
                f"[{index}/{len(items)}] {action}\t{item.id}\t"
                f"{item.name}\t{len(tags)} tags\t{provider}"
            )
            run_log.write(
                "item_completed",
                item=item_log_record(item, index=index, total=len(items)),
                action=action,
                changed=True,
                tags=tags,
                tag_count=len(tags),
                provider=provider_record(vision),
                provider_attempts=provider_attempt_records(vision),
                elapsed_ms=elapsed_ms_since(item_started),
            )
            if args.write:
                eagle.update_item(item.id, tags=tags, annotation=annotation)
                run_log.write(
                    "item_written",
                    item=item_log_record(item, index=index, total=len(items)),
                    tags=tags,
                    annotation_chars=len(annotation),
                )
        except Exception as exc:  # noqa: BLE001 - per-item isolation
            failed += 1
            print(f"[{index}/{len(items)}] failed\t{item.id}\t{redact(str(exc))}")
            run_log.write(
                "item_failed",
                item=item_log_record(item, index=index, total=len(items)),
                error=redact(str(exc)),
                provider_attempts=provider_attempt_records(vision),
                elapsed_ms=elapsed_ms_since(item_started),
            )
            if args.fail_fast:
                raise

    if not args.write:
        print("Dry run only. Re-run with --write to update Eagle.")
    print(f"Board: {board.path} ({board.id})")
    print(f"Changed: {changed}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    run_log.write(
        "run_complete",
        board={"id": board.id, "path": board.path, "name": board.name},
        changed=changed,
        skipped=skipped,
        failed=failed,
    )
    return 0 if failed == 0 else 1


def command_brief(args: argparse.Namespace) -> int:
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    items = eagle.list_items(board.id)
    markdown = build_brief(board, items)
    if args.output:
        output = Path(args.output)
        if output.is_dir():
            output = output / "moodboard-brief.md"
        output.write_text(markdown, encoding="utf-8")
        print(f"Wrote {output}")
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
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    items = eagle.list_items(board.id)
    changed = 0
    for item in items:
        if not item.annotation and not item.tags:
            continue
        changed += 1
        print(f"{'write' if args.write else 'dry-run'}\t{item.id}\t{item.name}")
        if args.write:
            eagle.update_item(item.id, tags=[], annotation="")
    if not args.write:
        print("Dry run only. Re-run with --write to clear annotations and tags.")
    print(f"Board: {board.path} ({board.id})")
    print(f"Reset candidates: {changed}")
    return 0


def command_config_set(args: argparse.Namespace) -> int:
    values = {
        "base_url": args.base_url,
        "fallback_base_url": args.fallback_base_url,
        "model": args.model,
        "fallback_model": args.fallback_model,
        "eagle_api": args.eagle_api,
    }
    values = {key: value for key, value in values.items() if value}
    if not values:
        raise MoodtagError("Pass at least one config value to set")
    path = update_user_config(values)
    print(f"Wrote {path}")
    return 0


def command_config_show(args: argparse.Namespace) -> int:
    config = load_user_config()
    primary_api_key_set = bool(os.environ.get("DASHSCOPE_API_KEY"))
    fallback_api_key_set = bool(
        os.environ.get("MOODTAG_API_KEY") or os.environ.get("VL_API_KEY")
    )
    view = public_config_view(
        config,
        api_key_set=primary_api_key_set or fallback_api_key_set,
        primary_api_key_set=primary_api_key_set,
        fallback_api_key_set=fallback_api_key_set,
    )
    if args.json:
        print(json.dumps(view, ensure_ascii=False, sort_keys=True))
        return 0
    print(f"Config: {view['config_path']}")
    print(f"base_url: {view['base_url'] or '-'}")
    print(f"fallback_base_url: {view['fallback_base_url'] or '-'}")
    print(f"model: {view['model'] or '-'}")
    print(f"fallback_model: {view['fallback_model'] or '-'}")
    print(f"eagle_api: {view['eagle_api'] or '-'}")
    print(f"api_key: {view['api_key']}")
    print(f"primary_api_key: {view['primary_api_key']}")
    print(f"fallback_api_key: {view['fallback_api_key']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moodtag")
    sub = parser.add_subparsers(dest="command", required=True)
    user_config = load_user_config()

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--board", required=True, help="Eagle folder id, name, or path")
        p.add_argument(
            "--eagle-api",
            default=config_value(
                user_config, "MOODTAG_EAGLE_API", "eagle_api", DEFAULT_EAGLE_API
            ),
        )

    status = sub.add_parser("status", help="Show board tagging status")
    common(status)
    status.add_argument("--verbose", action="store_true")
    status.set_defaults(func=command_status)

    tag = sub.add_parser("tag", help="Analyze pending board items")
    common(tag)
    tag.add_argument("--write", action="store_true", help="Actually update Eagle")
    tag.add_argument("--force", action="store_true", help="Reprocess existing notes")
    tag.add_argument("--mock-vl", action="store_true", help="Use deterministic mock VL")
    tag.add_argument(
        "--base-url",
        default=config_value(
            user_config, "MOODTAG_BASE_URL", "base_url", DEFAULT_BASE_URL
        ),
    )
    tag.add_argument(
        "--fallback-base-url",
        default=config_value(
            user_config,
            "MOODTAG_FALLBACK_BASE_URL",
            "fallback_base_url",
            DEFAULT_FALLBACK_BASE_URL,
        ),
    )
    tag.add_argument(
        "--model",
        default=config_value(user_config, "MOODTAG_MODEL", "model", DEFAULT_MODEL),
    )
    tag.add_argument(
        "--fallback-model",
        default=config_value(
            user_config,
            "MOODTAG_FALLBACK_MODEL",
            "fallback_model",
            DEFAULT_FALLBACK_MODEL,
        ),
    )
    tag.add_argument(
        "--taxonomy",
        default=os.environ.get("MOODTAG_TAXONOMY", DEFAULT_TAXONOMY),
    )
    tag.add_argument(
        "--image-edge",
        type=int,
        default=env_int("MOODTAG_IMAGE_EDGE", DEFAULT_IMAGE_EDGE, minimum=256),
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

    config = sub.add_parser("config", help="Manage non-secret moodtag defaults")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_set = config_sub.add_parser("set", help="Set non-secret user defaults")
    config_set.add_argument("--base-url", default="")
    config_set.add_argument("--fallback-base-url", default="")
    config_set.add_argument("--model", default="")
    config_set.add_argument("--fallback-model", default="")
    config_set.add_argument("--eagle-api", default="")
    config_set.set_defaults(func=command_config_set)
    config_show = config_sub.add_parser("show", help="Show non-secret user defaults")
    config_show.add_argument("--json", action="store_true")
    config_show.set_defaults(func=command_config_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        load_env_defaults()
        parser = build_parser()
        args = parser.parse_args(argv)
        return int(args.func(args) or 0)
    except MoodtagError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
