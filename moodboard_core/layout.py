from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONTAINER_WIDTH = 1180
DEFAULT_TARGET_ROW_HEIGHT = 300
DEFAULT_GAP = 12
DEFAULT_TOLERANCE = 0.25
DEFAULT_EAGLE_API = "http://localhost:41595"
IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".svg",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
}


class LayoutError(ValueError):
    """Expected layout input error."""


@dataclass(frozen=True)
class LayoutItem:
    id: str
    src: str
    width: int
    height: int
    alt: str = ""
    caption: str = ""
    fit: str = "cover"

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


def positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise LayoutError(f"{field} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LayoutError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise LayoutError(f"{field} must be a positive integer")
    return parsed


def one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def clean_src_value(value: Any) -> str:
    return str(value or "").strip()


def brief_from_annotation(value: Any) -> str:
    text = str(value or "")
    for line in text.splitlines():
        if line.lower().startswith("brief:"):
            return one_line(line.split(":", 1)[1]).rstrip("。.!！?？")
    return ""


def item_from_dict(raw: dict[str, Any], index: int) -> LayoutItem:
    width = positive_int(raw.get("width"), f"items[{index}].width")
    height = positive_int(raw.get("height"), f"items[{index}].height")
    ident = one_line(raw.get("id") or raw.get("name") or f"item-{index + 1:03d}")
    src = clean_src_value(raw.get("src") or raw.get("source") or raw.get("path") or "")
    if not src:
        raise LayoutError(f"items[{index}].src is required")
    brief = one_line(raw.get("brief") or brief_from_annotation(raw.get("annotation")))
    alt = one_line(raw.get("alt") or brief or raw.get("name") or ident)
    caption = one_line(raw.get("caption") or brief)
    fit = one_line(raw.get("fit") or "cover")
    if fit not in {"cover", "contain"}:
        raise LayoutError(f"items[{index}].fit must be cover or contain")
    return LayoutItem(
        id=ident,
        src=src,
        width=width,
        height=height,
        alt=alt,
        caption=caption,
        fit=fit,
    )


def load_items_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LayoutError(f"invalid JSON input: {exc}") from exc
    if isinstance(payload, list):
        return {"items": payload}
    if isinstance(payload, dict):
        return payload
    raise LayoutError("layout input must be a JSON object or array")


def parse_id_args(values: list[str] | None) -> list[str]:
    ids: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            ident = part.strip()
            if ident:
                ids.append(ident)
    return ids


def filter_raw_items_by_ids(
    raw_items: list[dict[str, Any]], ids: list[str]
) -> list[dict[str, Any]]:
    if not ids:
        return raw_items
    by_id = {one_line(item.get("id")): item for item in raw_items}
    missing = [ident for ident in ids if ident not in by_id]
    if missing:
        raise LayoutError(f"requested item ids not found: {', '.join(missing)}")
    return [by_id[ident] for ident in ids]


def load_items(path: str, *, ids: list[str] | None = None) -> list[LayoutItem]:
    payload = load_items_payload(path)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise LayoutError("layout input must contain an items array")
    raw_dicts = [raw for raw in raw_items if isinstance(raw, dict)]
    if len(raw_dicts) != len(raw_items):
        raise LayoutError("each layout item must be an object")
    raw_dicts = filter_raw_items_by_ids(raw_dicts, parse_id_args(ids))
    items = [item_from_dict(raw, index) for index, raw in enumerate(raw_dicts)]
    if not items:
        raise LayoutError("layout input must contain at least one item")
    return items


def row_height(
    ratios: list[float], *, container_width: int, gap: int, target_row_height: int
) -> float:
    if not ratios:
        return float(target_row_height)
    available = container_width - gap * (len(ratios) - 1)
    return max(1.0, available / sum(ratios))


def plan_justified(
    items: list[LayoutItem],
    *,
    container_width: int = DEFAULT_CONTAINER_WIDTH,
    target_row_height: int = DEFAULT_TARGET_ROW_HEIGHT,
    gap: int = DEFAULT_GAP,
    tolerance: float = DEFAULT_TOLERANCE,
    widow_mode: str = "left",
) -> dict[str, Any]:
    if container_width <= 0:
        raise LayoutError("container_width must be positive")
    if target_row_height <= 0:
        raise LayoutError("target_row_height must be positive")
    if gap < 0:
        raise LayoutError("gap must be zero or positive")
    if tolerance < 0:
        raise LayoutError("tolerance must be zero or positive")
    if widow_mode not in {"left", "justify"}:
        raise LayoutError("widow_mode must be left or justify")

    lower = target_row_height * (1 - tolerance)
    rows: list[list[LayoutItem]] = []
    current: list[LayoutItem] = []
    current_ratio = 0.0
    index = 0
    while index < len(items):
        item = items[index]
        candidate = [*current, item]
        candidate_ratio = current_ratio + item.aspect_ratio
        candidate_height = row_height(
            [entry.aspect_ratio for entry in candidate],
            container_width=container_width,
            gap=gap,
            target_row_height=target_row_height,
        )
        if current and candidate_height < lower:
            current_height = row_height(
                [entry.aspect_ratio for entry in current],
                container_width=container_width,
                gap=gap,
                target_row_height=target_row_height,
            )
            if abs(candidate_height - target_row_height) <= abs(
                current_height - target_row_height
            ):
                rows.append(candidate)
                current = []
                current_ratio = 0.0
                index += 1
            else:
                rows.append(current)
                current = []
                current_ratio = 0.0
        else:
            current = candidate
            current_ratio = candidate_ratio
            index += 1

    if current:
        rows.append(current)

    boxes: list[dict[str, Any]] = []
    row_payloads: list[dict[str, Any]] = []
    y = 0.0
    for row_index, row in enumerate(rows):
        is_last = row_index == len(rows) - 1
        ratios = [entry.aspect_ratio for entry in row]
        height = row_height(
            ratios,
            container_width=container_width,
            gap=gap,
            target_row_height=target_row_height,
        )
        left_aligned_widow = False
        if is_last and widow_mode == "left":
            natural_width = sum(ratio * target_row_height for ratio in ratios) + gap * (
                len(row) - 1
            )
            left_aligned_widow = natural_width <= container_width
        if left_aligned_widow:
            height = float(target_row_height)
        x = 0.0
        row_boxes: list[dict[str, Any]] = []
        for item_index, item in enumerate(row):
            width = height * item.aspect_ratio
            if not left_aligned_widow and item_index == len(row) - 1:
                width = max(1.0, container_width - x)
            box = {
                **item_to_spec(item),
                "row": row_index,
                "x": round(x, 3),
                "y": round(y, 3),
                "width": round(width, 3),
                "height": round(height, 3),
            }
            boxes.append(box)
            row_boxes.append(box)
            x += width + gap
        row_width = row_boxes[-1]["x"] + row_boxes[-1]["width"] if row_boxes else 0
        row_payloads.append(
            {
                "index": row_index,
                "y": round(y, 3),
                "height": round(height, 3),
                "width": round(row_width, 3),
                "item_count": len(row),
                "justified": not left_aligned_widow,
                "items": [entry.id for entry in row],
            }
        )
        y += height + gap

    total_height = max(0.0, y - gap)
    heights = [row["height"] for row in row_payloads]
    max_right = max((box["x"] + box["width"] for box in boxes), default=0)
    return {
        "ok": True,
        "kind": "geometry-plan",
        "html_output": False,
        "mode": "justified",
        "container_width": container_width,
        "target_row_height": target_row_height,
        "gap": gap,
        "tolerance": tolerance,
        "widow_mode": widow_mode,
        "width": container_width,
        "height": round(total_height, 3),
        "rows": row_payloads,
        "boxes": boxes,
        "metrics": {
            "item_count": len(items),
            "row_count": len(row_payloads),
            "min_row_height": min(heights) if heights else 0,
            "max_row_height": max(heights) if heights else 0,
            "max_right": round(max_right, 3),
            "horizontal_overflow": max_right > container_width + 0.5,
        },
    }


def orientation_for_ratio(ratio: float) -> str:
    if math.isclose(ratio, 1.0, rel_tol=0.02, abs_tol=0.02):
        return "square"
    return "landscape" if ratio > 1 else "portrait"


def item_to_spec(item: LayoutItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "src": item.src,
        "alt": item.alt,
        "caption": item.caption,
        "fit": item.fit,
        "source_width": item.width,
        "source_height": item.height,
        "width_attr": item.width,
        "height_attr": item.height,
        "aspect_ratio": round(item.aspect_ratio, 6),
        "css_aspect_ratio": f"{item.width} / {item.height}",
        "orientation": orientation_for_ratio(item.aspect_ratio),
    }


def specs_from_items(items: list[LayoutItem]) -> dict[str, Any]:
    ratios = [item.aspect_ratio for item in items]
    return {
        "ok": True,
        "kind": "image-specs",
        "html_output": False,
        "item_count": len(items),
        "items": [item_to_spec(item) for item in items],
        "metrics": {
            "min_aspect_ratio": round(min(ratios), 6),
            "max_aspect_ratio": round(max(ratios), 6),
            "portrait_count": sum(1 for ratio in ratios if ratio < 1),
            "landscape_count": sum(1 for ratio in ratios if ratio > 1),
            "square_count": sum(
                1
                for ratio in ratios
                if math.isclose(ratio, 1.0, rel_tol=0.02, abs_tol=0.02)
            ),
        },
    }


def plan_strip(
    items: list[LayoutItem],
    *,
    container_width: int = DEFAULT_CONTAINER_WIDTH,
    gap: int = DEFAULT_GAP,
) -> dict[str, Any]:
    if container_width <= 0:
        raise LayoutError("container_width must be positive")
    if gap < 0:
        raise LayoutError("gap must be zero or positive")
    ratios = [item.aspect_ratio for item in items]
    height = row_height(
        ratios,
        container_width=container_width,
        gap=gap,
        target_row_height=DEFAULT_TARGET_ROW_HEIGHT,
    )
    boxes: list[dict[str, Any]] = []
    x = 0.0
    for item_index, item in enumerate(items):
        width = height * item.aspect_ratio
        if item_index == len(items) - 1:
            width = max(1.0, container_width - x)
        boxes.append(
            {
                **item_to_spec(item),
                "row": 0,
                "x": round(x, 3),
                "y": 0,
                "width": round(width, 3),
                "height": round(height, 3),
            }
        )
        x += width + gap
    return {
        "ok": True,
        "kind": "geometry-plan",
        "html_output": False,
        "mode": "strip",
        "container_width": container_width,
        "gap": gap,
        "width": container_width,
        "height": round(height, 3),
        "rows": [
            {
                "index": 0,
                "y": 0,
                "height": round(height, 3),
                "width": container_width,
                "item_count": len(items),
                "justified": True,
                "items": [item.id for item in items],
            }
        ],
        "boxes": boxes,
        "metrics": {
            "item_count": len(items),
            "row_count": 1,
            "min_row_height": round(height, 3),
            "max_row_height": round(height, 3),
            "max_right": container_width,
            "horizontal_overflow": False,
        },
    }


def plan_stack(
    items: list[LayoutItem],
    *,
    container_width: int = DEFAULT_CONTAINER_WIDTH,
    gap: int = DEFAULT_GAP,
) -> dict[str, Any]:
    if container_width <= 0:
        raise LayoutError("container_width must be positive")
    if gap < 0:
        raise LayoutError("gap must be zero or positive")
    boxes: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    y = 0.0
    for index, item in enumerate(items):
        height = container_width / item.aspect_ratio
        box = {
            **item_to_spec(item),
            "row": index,
            "x": 0,
            "y": round(y, 3),
            "width": container_width,
            "height": round(height, 3),
        }
        boxes.append(box)
        rows.append(
            {
                "index": index,
                "y": round(y, 3),
                "height": round(height, 3),
                "width": container_width,
                "item_count": 1,
                "justified": True,
                "items": [item.id],
            }
        )
        y += height + gap
    total_height = max(0.0, y - gap)
    heights = [row["height"] for row in rows]
    return {
        "ok": True,
        "kind": "geometry-plan",
        "html_output": False,
        "mode": "stack",
        "container_width": container_width,
        "gap": gap,
        "width": container_width,
        "height": round(total_height, 3),
        "rows": rows,
        "boxes": boxes,
        "metrics": {
            "item_count": len(items),
            "row_count": len(rows),
            "min_row_height": min(heights) if heights else 0,
            "max_row_height": max(heights) if heights else 0,
            "max_right": container_width,
            "horizontal_overflow": False,
        },
    }


def parse_aspect_ratio(value: str) -> float:
    raw = str(value or "").strip().replace("/", ":")
    if not raw:
        raise LayoutError("cell_aspect_ratio is required")
    parts = [part.strip() for part in raw.split(":")]
    try:
        if len(parts) == 1:
            ratio = float(parts[0])
        elif len(parts) == 2:
            ratio = float(parts[0]) / float(parts[1])
        else:
            raise ValueError
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise LayoutError("cell_aspect_ratio must look like 1:1, 4:3, or 1.5") from exc
    if ratio <= 0:
        raise LayoutError("cell_aspect_ratio must be positive")
    return ratio


def plan_grid(
    items: list[LayoutItem],
    *,
    container_width: int = DEFAULT_CONTAINER_WIDTH,
    gap: int = DEFAULT_GAP,
    columns: int = 0,
    cell_aspect_ratio: str = "1:1",
) -> dict[str, Any]:
    if container_width <= 0:
        raise LayoutError("container_width must be positive")
    if gap < 0:
        raise LayoutError("gap must be zero or positive")
    if columns <= 0:
        columns = min(3, len(items))
    if columns <= 0:
        raise LayoutError("columns must be positive")
    ratio = parse_aspect_ratio(cell_aspect_ratio)
    cell_width = (container_width - gap * (columns - 1)) / columns
    cell_height = cell_width / ratio
    boxes: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    row_count = math.ceil(len(items) / columns)
    for row_index in range(row_count):
        row_items = items[row_index * columns : (row_index + 1) * columns]
        y = row_index * (cell_height + gap)
        rows.append(
            {
                "index": row_index,
                "y": round(y, 3),
                "height": round(cell_height, 3),
                "width": container_width,
                "item_count": len(row_items),
                "justified": len(row_items) == columns,
                "items": [item.id for item in row_items],
            }
        )
        for column_index, item in enumerate(row_items):
            boxes.append(
                {
                    **item_to_spec(item),
                    "row": row_index,
                    "column": column_index,
                    "x": round(column_index * (cell_width + gap), 3),
                    "y": round(y, 3),
                    "width": round(cell_width, 3),
                    "height": round(cell_height, 3),
                }
            )
    total_height = row_count * cell_height + max(0, row_count - 1) * gap
    return {
        "ok": True,
        "kind": "geometry-plan",
        "html_output": False,
        "mode": "grid",
        "container_width": container_width,
        "gap": gap,
        "columns": columns,
        "cell_aspect_ratio": cell_aspect_ratio,
        "width": container_width,
        "height": round(total_height, 3),
        "rows": rows,
        "boxes": boxes,
        "metrics": {
            "item_count": len(items),
            "row_count": row_count,
            "min_row_height": round(cell_height, 3),
            "max_row_height": round(cell_height, 3),
            "max_right": container_width,
            "horizontal_overflow": False,
        },
    }


def folder_id_from_value(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise LayoutError("folder id or URL is required")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        query = urllib.parse.parse_qs(parsed.query)
        folder_id = (query.get("id") or [""])[0].strip()
        if folder_id:
            return folder_id
        path_id = parsed.path.rstrip("/").split("/")[-1]
        if path_id and path_id != "folder":
            return path_id
        raise LayoutError(f"cannot extract folder id from URL: {value}")
    if raw.startswith("eagle://folder/"):
        return raw.rsplit("/", 1)[-1].strip()
    return raw


def eagle_base_from_folder_value(value: str, default_base: str) -> str:
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return default_base.rstrip("/")


def http_json(
    url: str, *, method: str = "GET", payload: dict[str, Any] | None = None
) -> Any:
    data = None
    headers = {"User-Agent": "moodboard-layout/0.1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def expect_eagle_success(payload: Any, label: str) -> Any:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise LayoutError(f"Eagle {label} failed: {str(payload)[:500]}")
    return payload.get("data")


def original_from_thumbnail(thumbnail: str, item: dict[str, Any]) -> str:
    thumb_path = Path(thumbnail)
    info_dir = thumb_path.parent
    if not info_dir.exists() or not info_dir.is_dir():
        return thumbnail
    preferred_ext = "." + one_line(item.get("ext")).lower().lstrip(".")
    name = one_line(item.get("name"))
    candidates: list[Path] = []
    for path in info_dir.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == "metadata.json" or "_thumbnail" in lower:
            continue
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        candidates.append(path)
    if not candidates:
        return thumbnail
    exact = [path for path in candidates if path.suffix.lower() == preferred_ext]
    if exact:
        candidates = exact
    name_matches = [path for path in candidates if path.stem == name]
    if name_matches:
        original = name_matches[0]
    else:
        original = max(candidates, key=lambda path: path.stat().st_size)
    return str(original) if original.exists() else thumbnail


def eagle_thumbnail_path(base: str, item_id: str) -> str:
    thumb_query = urllib.parse.urlencode({"id": item_id})
    thumb_data = http_json(f"{base}/api/item/thumbnail?{thumb_query}")
    thumb = str(expect_eagle_success(thumb_data, "item thumbnail") or "")
    if thumb.startswith("file://"):
        thumb = thumb[len("file://") :]
    return urllib.parse.unquote(thumb)


def catalog_item_from_eagle(
    raw: dict[str, Any], *, base: str, image_source: str
) -> dict[str, Any] | None:
    ident = one_line(raw.get("id"))
    if not ident:
        return None
    try:
        width = positive_int(raw.get("width"), f"{ident}.width")
        height = positive_int(raw.get("height"), f"{ident}.height")
    except LayoutError:
        return None
    src = ""
    source_kind = image_source
    try:
        thumbnail = eagle_thumbnail_path(base, ident)
        if image_source == "original":
            src = original_from_thumbnail(thumbnail, raw)
            source_kind = "original" if src != thumbnail else "thumbnail"
        else:
            src = thumbnail
            source_kind = "thumbnail"
    except Exception:
        src = ""
    if not src or not Path(src).exists():
        return None
    brief = brief_from_annotation(raw.get("annotation"))
    return {
        "id": ident,
        "name": raw.get("name") or ident,
        "src": src,
        "source_kind": source_kind,
        "width": width,
        "height": height,
        "brief": brief,
        "alt": brief or raw.get("name") or ident,
        "caption": brief,
        "annotation": raw.get("annotation") or "",
        "tags": raw.get("tags") or [],
    }


def eagle_items(
    folder_value: str,
    *,
    eagle_api: str = DEFAULT_EAGLE_API,
    limit: int = 500,
    image_source: str = "original",
) -> list[dict[str, Any]]:
    if limit <= 0:
        raise LayoutError("limit must be positive")
    if image_source not in {"original", "thumbnail"}:
        raise LayoutError("image_source must be original or thumbnail")
    folder_id = folder_id_from_value(folder_value)
    base = eagle_base_from_folder_value(folder_value, eagle_api).rstrip("/")
    try:
        data = http_json(
            f"{base}/api/v2/item/get",
            method="POST",
            payload={"folders": [folder_id], "limit": limit, "offset": 0},
        )
        raw = expect_eagle_success(data, "item get")
        if isinstance(raw, dict) and isinstance(raw.get("data"), list):
            items = raw["data"]
        else:
            items = []
    except Exception:
        query = urllib.parse.urlencode({"folders": folder_id, "limit": limit})
        data = http_json(f"{base}/api/item/list?{query}")
        raw = expect_eagle_success(data, "item list")
        items = raw if isinstance(raw, list) else []

    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        catalog_item = catalog_item_from_eagle(
            item, base=base, image_source=image_source
        )
        if catalog_item is not None:
            result.append(catalog_item)
    if not result:
        raise LayoutError(f"no usable Eagle items found for folder {folder_id}")
    return result


def write_text_or_stdout(path: str, text: str) -> None:
    if path:
        Path(path).expanduser().write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def write_json_or_stdout(path: str, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_text_or_stdout(path, text)


def command_plan(args: argparse.Namespace) -> int:
    items = load_items(args.input, ids=args.ids)
    if args.mode == "justified":
        plan = plan_justified(
            items,
            container_width=args.container_width,
            target_row_height=args.target_row_height,
            gap=args.gap,
            tolerance=args.tolerance,
            widow_mode=args.widow_mode,
        )
    elif args.mode == "strip":
        plan = plan_strip(
            items,
            container_width=args.container_width,
            gap=args.gap,
        )
    elif args.mode == "stack":
        plan = plan_stack(
            items,
            container_width=args.container_width,
            gap=args.gap,
        )
    elif args.mode == "grid":
        plan = plan_grid(
            items,
            container_width=args.container_width,
            gap=args.gap,
            columns=args.columns,
            cell_aspect_ratio=args.cell_aspect_ratio,
        )
    else:
        raise LayoutError(f"unknown layout mode: {args.mode}")
    write_json_or_stdout(args.output, plan)
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    items = load_items(args.input, ids=args.ids)
    write_json_or_stdout(args.output, specs_from_items(items))
    return 0


def command_catalog(args: argparse.Namespace) -> int:
    raw_items = eagle_items(
        args.folder,
        eagle_api=args.eagle_api,
        limit=args.limit,
        image_source=args.image_source,
    )
    raw_items = filter_raw_items_by_ids(raw_items, parse_id_args(args.ids))
    payload = {
        "ok": True,
        "kind": "image-catalog",
        "html_output": False,
        "source": "eagle",
        "folder_id": folder_id_from_value(args.folder),
        "item_count": len(raw_items),
        "items": raw_items,
    }
    write_json_or_stdout(args.output, payload)
    if args.json and args.output:
        print(
            json.dumps(
                {
                    "ok": True,
                    "folder_id": payload["folder_id"],
                    "item_count": payload["item_count"],
                    "output": args.output,
                },
                ensure_ascii=False,
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moodboard-layout",
        description="Compute deterministic image specs and geometry plans",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="Export layout-ready items from Eagle")
    catalog.add_argument("--folder", required=True, help="Eagle folder id or URL")
    catalog.add_argument("--eagle-api", default=DEFAULT_EAGLE_API)
    catalog.add_argument("--limit", type=int, default=500)
    catalog.add_argument("--ids", nargs="*", default=[], help="Optional item ids")
    catalog.add_argument(
        "--image-source", choices=["original", "thumbnail"], default="original"
    )
    catalog.add_argument("--output", default="", help="Write catalog JSON to this path")
    catalog.add_argument("--json", action="store_true", help="Print summary JSON")
    catalog.set_defaults(func=command_catalog)

    inspect = sub.add_parser(
        "inspect", help="Export selected image specs without deciding HTML"
    )
    inspect.add_argument("--input", required=True, help="JSON file or - for stdin")
    inspect.add_argument("--output", default="", help="Write specs JSON to this path")
    inspect.add_argument("--ids", nargs="*", default=[], help="Optional item ids")
    inspect.set_defaults(func=command_inspect)

    plan = sub.add_parser(
        "plan", help="Compute a geometry plan from selected image specs"
    )
    plan.add_argument("--input", required=True, help="JSON file or - for stdin")
    plan.add_argument("--output", default="", help="Write plan JSON to this path")
    plan.add_argument("--ids", nargs="*", default=[], help="Optional item ids")
    add_layout_args(plan)
    plan.set_defaults(func=command_plan)
    return parser


def add_layout_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=["justified", "strip", "stack", "grid"],
        default="justified",
        help="Geometry mode; agent still owns the surrounding HTML",
    )
    parser.add_argument("--container-width", type=int, default=DEFAULT_CONTAINER_WIDTH)
    parser.add_argument(
        "--target-row-height", type=int, default=DEFAULT_TARGET_ROW_HEIGHT
    )
    parser.add_argument("--gap", type=int, default=DEFAULT_GAP)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--widow-mode", choices=["left", "justify"], default="left")
    parser.add_argument(
        "--columns",
        type=int,
        default=0,
        help="Grid mode column count; defaults to up to 3 columns",
    )
    parser.add_argument(
        "--cell-aspect-ratio",
        default="1:1",
        help="Grid mode cell ratio such as 1:1, 4:3, or 3:4",
    )


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        return int(args.func(args) or 0)
    except LayoutError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
