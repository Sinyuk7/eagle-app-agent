from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path

IMG_SRC_RE = re.compile(
    r"""(<img\b[^>]*\bsrc\s*=\s*["'])([^"']+)(["'][^>]*>)""", re.IGNORECASE
)
REMOTE_SCHEMES = {"http", "https"}
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


def is_remote(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme in REMOTE_SCHEMES


def clean_src(value: str) -> str:
    return html.unescape((value or "").strip())


def resolve_local_src(value: str, project_dir: Path) -> Path | None:
    value = clean_src(value)
    if not value or is_remote(value) or value.startswith("#"):
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        return None
    raw = urllib.parse.unquote(parsed.path if parsed.scheme == "file" else value)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def is_project_relative(value: str) -> bool:
    parsed = urllib.parse.urlparse(clean_src(value))
    return (
        not parsed.scheme
        and not Path(urllib.parse.unquote(parsed.path)).expanduser().is_absolute()
    )


def safe_asset_name(path: Path, index: int) -> str:
    stem = (
        re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip(".-") or f"asset-{index:03d}"
    )
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    suffix = path.suffix.lower() if path.suffix.lower() in IMAGE_EXTS else ".jpg"
    return f"{index:03d}-{stem[:60]}-{digest}{suffix}"


def materialize_image(
    path: Path, project_dir: Path, index: int, mode: str, cache_dir: str
) -> dict:
    assets_dir = project_dir / cache_dir
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / safe_asset_name(path, index)
    if mode == "copy":
        if not target.exists() or target.stat().st_size != path.stat().st_size:
            shutil.copy2(path, target)
        action = "copy"
    elif mode == "symlink":
        if target.exists() or target.is_symlink():
            if target.is_symlink() and Path(os.readlink(target)) == path:
                pass
            else:
                target.unlink()
        if not target.exists():
            target.symlink_to(path)
        action = "symlink"
    else:
        raise ValueError(f"unsupported local image mode: {mode}")
    return {
        "source": str(path),
        "path": str(target),
        "uri": target.relative_to(project_dir).as_posix(),
        "mode": action,
        "bytes": path.stat().st_size,
    }


def write_manifest(project_dir: Path, cache_dir: str, assets: list[dict]) -> str | None:
    if not assets:
        return None
    manifest_path = project_dir / cache_dir / "manifest.json"
    existing: list[dict] = []
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("assets"), list):
                existing = payload["assets"]
        except Exception:
            existing = []
    by_uri = {
        str(item.get("uri")): item
        for item in existing
        if isinstance(item, dict) and item.get("uri")
    }
    for asset in assets:
        by_uri[asset["uri"]] = asset
    manifest = {"ok": True, "assets": list(by_uri.values())}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(manifest_path)


def process_image_sources(
    body: str, project_dir: Path, mode: str, cache_dir: str
) -> tuple[str, dict]:
    rewrites: list[dict] = []
    skipped_remote: list[dict] = []
    missing: list[dict] = []
    materialized: list[dict] = []
    materialize_index = 0

    def repl(match: re.Match) -> str:
        nonlocal materialize_index
        prefix, raw_src, suffix = match.group(1), match.group(2), match.group(3)
        src = clean_src(raw_src)
        if is_remote(src):
            skipped_remote.append({"src": src, "reason": "remote_kept"})
            return match.group(0)
        if is_project_relative(src):
            local = resolve_local_src(src, project_dir)
            if local and local.exists():
                return match.group(0)
            missing.append(
                {
                    "src": src,
                    "resolved": str(local) if local else None,
                    "reason": "missing_project_relative",
                }
            )
            return match.group(0)
        local = resolve_local_src(src, project_dir)
        if not local or not local.exists() or local.suffix.lower() not in IMAGE_EXTS:
            missing.append(
                {
                    "src": src,
                    "resolved": str(local) if local else None,
                    "reason": "missing_or_not_image",
                }
            )
            return match.group(0)
        materialize_index += 1
        asset = materialize_image(
            local, project_dir, materialize_index, mode, cache_dir
        )
        materialized.append(asset)
        rewrites.append(
            {
                "from": src,
                "to": asset["uri"],
                "path": asset["path"],
                "mode": asset["mode"],
            }
        )
        return f"{prefix}{html.escape(asset['uri'], quote=True)}{suffix}"

    updated = IMG_SRC_RE.sub(repl, body)
    manifest_path = write_manifest(project_dir, cache_dir, materialized)
    return updated, {
        "rewrites": rewrites,
        "materialized": materialized,
        "missing": missing,
        "remote_kept": skipped_remote,
        "manifest_path": manifest_path,
    }
