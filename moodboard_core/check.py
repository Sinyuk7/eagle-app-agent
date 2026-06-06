#!/usr/bin/env python3
"""Run local sanity checks for a moodboard index.html."""

import argparse
import html.parser
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REMOTE_SCHEMES = {"http", "https"}
IGNORED_LINK_SCHEMES = {"data", "mailto", "tel", "sms", "javascript"}


class HTMLCollector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.images = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs}
        line, _col = self.getpos()
        if "id" in attrs_dict and attrs_dict["id"]:
            self.ids.append({"id": attrs_dict["id"], "line": line, "tag": tag.lower()})
        if tag.lower() == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src") or "",
                    "alt": attrs_dict.get("alt"),
                    "line": line,
                    "tag": tag.lower(),
                }
            )
        if tag.lower() == "a":
            self.links.append(
                {"tag": tag.lower(), "href": attrs_dict.get("href") or "", "line": line}
            )
        if tag.lower() == "link" and "href" in attrs_dict:
            self.links.append(
                {
                    "tag": tag.lower(),
                    "href": attrs_dict.get("href") or "",
                    "rel": attrs_dict.get("rel"),
                    "line": line,
                }
            )


def is_remote(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme in REMOTE_SCHEMES


def is_ignored_or_anchor(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in IGNORED_LINK_SCHEMES or value.startswith("#")


def is_localhost_unsafe_ref(value: str) -> bool:
    """True for local filesystem references unsafe in a page served over http://127.0.0.1."""
    if not value or is_remote(value) or is_ignored_or_anchor(value):
        return False
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "file":
        return True
    raw = urllib.parse.unquote(parsed.path or value)
    return Path(raw).expanduser().is_absolute()


def resolve_local(value: str, index_path: Path) -> Path | None:
    if not value or is_remote(value) or is_ignored_or_anchor(value):
        return None
    parsed = urllib.parse.urlparse(value)
    raw = urllib.parse.unquote(parsed.path)
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = index_path.parent / path
    return path.resolve()


def network_check(url: str, timeout: int = 8) -> dict:
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "Hermes moodboard checker"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"url": url, "ok": 200 <= resp.status < 400, "status": resp.status}
    except Exception as head_exc:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Hermes moodboard checker",
                    "Range": "bytes=0-0",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {
                    "url": url,
                    "ok": 200 <= resp.status < 400,
                    "status": resp.status,
                    "fallback": "GET",
                }
        except Exception as get_exc:
            return {
                "url": url,
                "ok": False,
                "error": str(get_exc),
                "head_error": str(head_exc),
            }


def duplicate_ids(ids: list[dict]) -> list[dict]:
    occurrences: dict[str, list[dict]] = {}
    for item in ids:
        occurrences.setdefault(item["id"], []).append(item)
    return [
        {"id": ident, "occurrences": items}
        for ident, items in occurrences.items()
        if len(items) > 1
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to index.html or its project directory")
    parser.add_argument(
        "--allow-empty-body",
        action="store_true",
        help="Allow an empty body for starter shells",
    )
    parser.add_argument(
        "--check-assets",
        action="store_true",
        help="Check img src, alt, and local image existence",
    )
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Check local relative href links resolve",
    )
    parser.add_argument(
        "--network-assets",
        action="store_true",
        help="Validate remote image URLs with HEAD/GET",
    )
    parser.add_argument(
        "--localhost-mode",
        action="store_true",
        help="Fail if local img/link references use file:// or absolute filesystem paths that may not load from http://127.0.0.1",
    )
    args = parser.parse_args(argv)

    path = Path(args.path).expanduser()
    index_path = path / "index.html" if path.is_dir() else path

    if not index_path.exists():
        print(
            json.dumps(
                {"ok": False, "error": "missing_file", "index_html": str(index_path)}
            )
        )
        return 2

    text = index_path.read_text(encoding="utf-8")
    head_start = re.search(r"<head[\s>]", text, re.I)
    head_end = re.search(r"</head\s*>", text, re.I)
    body_scope = text[head_end.end() :] if head_end else text
    body_start = re.search(r"<body[\s>]", body_scope, re.I)
    body_end = re.search(r"</body\s*>", body_scope, re.I)
    body_region = re.search(r"<body[\s\S]*?>[\s\S]*\S[\s\S]*?</body>", body_scope, re.I)
    checks = {
        "doctype": bool(re.search(r"<!doctype\s+html", text, re.I)),
        "html": bool(re.search(r"<html[\s>]", text, re.I)),
        "head": bool(head_start),
        "head_closed": bool(head_end),
        "body": bool(body_start),
        "body_closed": bool(body_end),
        "html_closed": bool(re.search(r"</html\s*>", text, re.I)),
        "viewport": 'name="viewport"' in text or "name='viewport'" in text,
        "nonempty_body": args.allow_empty_body or bool(body_region),
    }
    checks["head_before_body"] = bool(
        head_start and head_end and body_start and head_start.start() < head_end.end()
    )

    collector = HTMLCollector()
    collector.feed(text)

    known_ids = {item["id"] for item in collector.ids}
    duplicates = duplicate_ids(collector.ids)

    asset_checks = []
    missing_alt = []
    empty_src = []
    missing_local_assets = []
    remote_assets_skipped = []
    localhost_unsafe_assets = []
    localhost_unsafe_links = []
    if args.check_assets:
        for idx, img in enumerate(collector.images, start=1):
            src = (img.get("src") or "").strip()
            alt = img.get("alt")
            item = {
                "index": idx,
                "src": src,
                "line": img["line"],
                "kind": None,
                "ok": True,
                "path": None,
                "resolved": None,
                "error": None,
                "skipped": False,
            }
            if not src.strip():
                item.update({"kind": "empty", "ok": False, "error": "empty_src"})
                empty_src.append({"index": idx, "line": img["line"]})
                missing_local_assets.append(item)
                asset_checks.append(item)
                continue
            if alt is None or not alt.strip():
                missing_alt.append({"index": idx, "src": src, "line": img["line"]})
            if args.localhost_mode and is_localhost_unsafe_ref(src):
                localhost_unsafe_assets.append(
                    {
                        "index": idx,
                        "src": src,
                        "line": img["line"],
                        "error": "localhost_unsafe_filesystem_ref",
                    }
                )
            if is_remote(src):
                item["kind"] = "remote"
                if args.network_assets:
                    result = network_check(src)
                    item.update(
                        {
                            "ok": result["ok"],
                            "status": result.get("status"),
                            "error": result.get("error"),
                            "fallback": result.get("fallback"),
                        }
                    )
                    if not result["ok"]:
                        missing_local_assets.append(item)
                else:
                    item.update({"skipped": True, "remote_skipped": True})
                    remote_assets_skipped.append({"src": src, "line": img["line"]})
            else:
                item["kind"] = "local"
                local = resolve_local(src, index_path)
                ok = bool(local and local.exists())
                item.update(
                    {
                        "path": str(local) if local else None,
                        "resolved": str(local) if local else None,
                        "ok": ok,
                        "error": None if ok else "missing_local_asset",
                    }
                )
                if not ok:
                    missing_local_assets.append(item)
            asset_checks.append(item)

    link_checks = []
    link_failures = []
    remote_links_skipped = []
    if args.check_links:
        for link in collector.links:
            href = (link["href"] or "").strip()
            item = {
                **link,
                "href": href,
                "kind": None,
                "ok": True,
                "path": None,
                "resolved": None,
                "error": None,
                "skipped": False,
            }
            if args.localhost_mode and is_localhost_unsafe_ref(href):
                localhost_unsafe_links.append(
                    {**link, "href": href, "error": "localhost_unsafe_filesystem_ref"}
                )
            if not href:
                item.update({"kind": "empty", "ok": False, "error": "empty_href"})
                link_failures.append(item)
            elif href.startswith("#"):
                target = href[1:]
                item["kind"] = "fragment"
                if href.startswith("#") and len(href) > 1:
                    item.update(
                        {
                            "ok": target in known_ids,
                            "error": None
                            if target in known_ids
                            else "missing_fragment_target",
                        }
                    )
                    if not item["ok"]:
                        link_failures.append(item)
                else:
                    item.update({"skipped": True})
            elif is_remote(href):
                item["kind"] = "remote"
                if args.network_assets:
                    result = network_check(href)
                    item.update(
                        {
                            "ok": result["ok"],
                            "status": result.get("status"),
                            "error": result.get("error"),
                            "fallback": result.get("fallback"),
                        }
                    )
                    if not result["ok"]:
                        link_failures.append(item)
                else:
                    item.update({"skipped": True, "remote_skipped": True})
                    remote_links_skipped.append(
                        {"href": href, "line": link["line"], "tag": link["tag"]}
                    )
            elif urllib.parse.urlparse(href).scheme in IGNORED_LINK_SCHEMES:
                item.update(
                    {"kind": urllib.parse.urlparse(href).scheme, "skipped": True}
                )
            else:
                item["kind"] = "local"
                local = resolve_local(href, index_path)
                ok = bool(local and local.exists())
                item.update(
                    {
                        "path": str(local) if local else None,
                        "resolved": str(local) if local else None,
                        "ok": ok,
                        "error": None if ok else "missing_local_link",
                    }
                )
                if not ok:
                    link_failures.append(item)
            link_checks.append(item)

    checks["duplicate_ids"] = not duplicates
    if args.check_assets:
        checks["assets"] = (
            all(item.get("ok") for item in asset_checks)
            and not missing_alt
            and not empty_src
        )
    if args.check_links:
        checks["links"] = all(item.get("ok") for item in link_checks)
    if args.localhost_mode:
        checks["localhost_safe_assets"] = not localhost_unsafe_assets
        checks["localhost_safe_links"] = not localhost_unsafe_links

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "index_html": str(index_path),
                "checks": checks,
                "asset_checks": asset_checks,
                "link_checks": link_checks,
                "duplicate_ids": duplicates,
                "missing_alt": missing_alt,
                "empty_src": empty_src,
                "missing_local_assets": missing_local_assets,
                "remote_assets_skipped": remote_assets_skipped,
                "remote_skipped": [item["src"] for item in remote_assets_skipped],
                "link_failures": link_failures,
                "remote_links_skipped": remote_links_skipped,
                "localhost_unsafe_assets": localhost_unsafe_assets,
                "localhost_unsafe_links": localhost_unsafe_links,
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
