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
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterator

from .config import (
    ConfigError,
    load_user_config,
    public_config_view,
    update_user_config,
)
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
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    CoreError,
    MoodtagAnalysis,
)
from moodtag_core.provider import (
    VisionClient as CoreVisionClient,
    chat_completions_url,
    file_to_data_url,
    http_request,
    models_url,
    redact,
    url_join,
)
from moodtag_core.response import normalize_analysis_json, parse_analysis_response
from moodtag_core.taxonomy import (
    flatten_taxonomy,
    load_taxonomy,
    reconcile_tags as core_reconcile_tags,
    render_taxonomy_for_prompt,
    reconcile_use_intents,
)

DEFAULT_EAGLE_API = "http://localhost:41595"
DEFAULT_IMAGE_EDGE = 1024
DEFAULT_MAX_TAGS = 15
DEFAULT_RETRIES = 2
DEFAULT_USER_AGENT = "moodtag/0.1"
DEFAULT_TAXONOMY = "default"
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


@dataclass(frozen=True)
class Preview:
    path: Path
    source_path: Path
    source_width: int
    source_height: int
    width: int
    height: int
    mimetype: str = "image/jpeg"


def redact(text: str) -> str:
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", str(text))


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
        v1_base = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/v1", "", "")
        )
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
        v1_base = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/v1", "", "")
        )
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
        raise MoodtagError(f"HTTP {exc.code} from {url}: {redact(detail[:800])}") from exc
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
        data = http_request("GET", url_join(self.base_url, "/api/v2/app/info"), timeout=5)
        self._expect_success(data, "app info")
        return data["data"]

    def library_info(self) -> dict[str, Any]:
        data = http_request("GET", url_join(self.base_url, "/api/library/info"), timeout=10)
        self._expect_success(data, "library info")
        return data["data"]

    def boards(self) -> list[Board]:
        info = self.library_info()
        library_name = str(info.get("library", {}).get("name") or "").strip()
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

        roots = info.get("folders") or []
        if isinstance(roots, list):
            visit(roots)
        if library_name:
            boards.extend(
                Board(id=b.id, name=b.name, path=f"{library_name}/{b.path}", parent=b.parent)
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
            raise MoodtagError(f"Eagle {label} failed: {redact(json.dumps(data)[:800])}")


def parse_item(raw: dict[str, Any]) -> EagleItem:
    return EagleItem(
        id=str(raw.get("id", "")).strip(),
        name=str(raw.get("name", "")).strip(),
        ext=str(raw.get("ext", "")).strip().lower().lstrip("."),
        tags=[str(tag) for tag in raw.get("tags", []) if str(tag).strip()],
        folders=[str(folder) for folder in raw.get("folders", []) if str(folder).strip()],
        annotation=str(raw.get("annotation", "") or ""),
        width=raw.get("width"),
        height=raw.get("height"),
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
    return resources.files("moodtag_core.resources.taxonomy").joinpath(
        "default.json"
    ).read_text(encoding="utf-8")


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
    info_dir = thumbnail.parent
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
    except ImportError:
        if shutil.which("sips"):
            return create_preview_with_sips(source, dest, image_edge=image_edge)
        raise MoodtagError(
            "Image resizing requires Pillow. Install it with `python -m pip install Pillow`."
        )


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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not dest.exists():
        raise MoodtagError(f"sips failed to create preview: {proc.stderr.strip()}")
    return Preview(dest, source, source_width, source_height, width, height)


def sips_dimensions(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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

    def analyze(
        self,
        image: Path,
        taxonomy: dict[str, list[str]],
        retries: int,
        max_tags: int = DEFAULT_MAX_TAGS,
    ) -> MoodtagAnalysis:
        del image, retries
        first_tags = [
            tags[0]
            for _, tags in list(taxonomy.items())[:3]
            if tags
        ]
        return normalize_analysis_json(
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
    api_key = os.environ.get("MOODTAG_API_KEY") or os.environ.get("VL_API_KEY")
    return VisionClient(
        base_url=args.base_url,
        fallback_base_url=args.fallback_base_url,
        model=model,
        api_key=api_key,
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
    if args.max_tokens < 1:
        raise MoodtagError("--max-tokens must be at least 1")


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
) -> str:
    rows: list[tuple[EagleItem, dict[str, str], bool]] = []
    skipped_pending = 0
    for item in items:
        fields = parse_annotation_fields(item.annotation)
        complete = all(fields.get(label) for label in ANNOTATION_LABEL_ORDER)
        if not complete and not include_pending:
            skipped_pending += 1
            continue
        rows.append((item, fields, complete))

    lines = [
        f"# Moodboard Context: {board.path}",
        "",
        f"Items: {len(items)}",
        f"Exported: {len(rows)}",
        f"Pending skipped: {skipped_pending}",
        "",
    ]

    for index, (item, fields, complete) in enumerate(rows, start=1):
        lines.append(f"## {index}. {one_line(item.name)}")
        lines.append(f"ID: {item.id}")
        if not complete:
            lines.append("Status: pending")
        lines.append("Tags: " + (", ".join(one_line(tag) for tag in item.tags) or "-"))
        for label in ANNOTATION_LABEL_ORDER:
            value = one_line(fields.get(label, ""))
            if value or include_pending:
                lines.append(f"{label}: {value or '-'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def one_line(value: str) -> str:
    return " ".join(str(value or "").split())


def command_export_context(args: argparse.Namespace) -> int:
    eagle = public_attr("EagleClient")(args.eagle_api)
    eagle.app_info()
    board = resolve_board(args.board, eagle.boards())
    markdown = build_context_markdown(
        board,
        eagle.list_items(board.id),
        include_pending=args.include_pending,
    )
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(markdown, end="")
    return 0


def command_tag(args: argparse.Namespace) -> int:
    validate_tag_args(args)
    taxonomy = load_taxonomy(Path(args.taxonomy))
    vision = public_attr("make_vision_client")(args)
    eagle = public_attr("EagleClient")(args.eagle_api)
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

    for index, item in enumerate(items, start=1):
        if has_moodboard_notes(item.annotation) and not args.force:
            skipped += 1
            print(f"[{index}/{len(items)}] skip\t{item.id}\t{item.name}")
            continue
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
            print(
                f"[{index}/{len(items)}] {action}\t{item.id}\t"
                f"{item.name}\t{len(tags)} tags"
            )
            if args.write:
                eagle.update_item(item.id, tags=tags, annotation=annotation)
        except Exception as exc:  # noqa: BLE001 - per-item isolation
            failed += 1
            print(f"[{index}/{len(items)}] failed\t{item.id}\t{redact(str(exc))}")
            if args.fail_fast:
                raise

    if not args.write:
        print("Dry run only. Re-run with --write to update Eagle.")
    print(f"Board: {board.path} ({board.id})")
    print(f"Changed: {changed}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
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
    view = public_config_view(
        config,
        api_key_set=bool(os.environ.get("MOODTAG_API_KEY") or os.environ.get("VL_API_KEY")),
    )
    if args.json:
        print(json.dumps(view, ensure_ascii=False, sort_keys=True))
        return 0
    print(f"Config: {view['config_path']}")
    print(f"base_url: {view['base_url'] or '-'}")
    print(f"fallback_base_url: {view['fallback_base_url'] or '-'}")
    print(f"model: {view['model'] or '-'}")
    print(f"eagle_api: {view['eagle_api'] or '-'}")
    print(f"api_key: {view['api_key']}")
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
        default=config_value(user_config, "MOODTAG_BASE_URL", "base_url", DEFAULT_BASE_URL),
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
        default=env_int("MOODTAG_MAX_TOKENS", DEFAULT_MAX_TOKENS, minimum=1),
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

    reset = sub.add_parser("reset", help="Remove moodtag annotation fields from board items")
    common(reset)
    reset.add_argument("--write", action="store_true")
    reset.set_defaults(func=command_reset)

    config = sub.add_parser("config", help="Manage non-secret moodtag defaults")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_set = config_sub.add_parser("set", help="Set non-secret user defaults")
    config_set.add_argument("--base-url", default="")
    config_set.add_argument("--fallback-base-url", default="")
    config_set.add_argument("--model", default="")
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
