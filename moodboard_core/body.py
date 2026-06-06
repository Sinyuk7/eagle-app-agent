#!/usr/bin/env python3
"""Replace only the contents inside <body> of an existing index.html."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .image_utils import process_image_sources

BODY_RE = re.compile(r"(<body\b[^>]*>)([\s\S]*?)(</body\s*>)", re.IGNORECASE)
HEAD_END_RE = re.compile(r"</head\s*>", re.IGNORECASE)
UPDATED_META_RE = re.compile(
    r"""<meta\b(?=[^>]*\bname=["']moodboard-updated-at["'])(?=[^>]*\bcontent=["'])[^>]*>""",
    re.IGNORECASE,
)
BODY_OPEN_RE = re.compile(r"""<body\b[^>]*>""", re.IGNORECASE)
ATTR_VALUE_RE_TEMPLATE = r"""({attr}\s*=\s*["'])([^"']*)(["'])"""


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("body content is required via --body-file or stdin")


def replace_attr(tag: str, attr: str, value: str) -> tuple[str, int]:
    pattern = re.compile(
        ATTR_VALUE_RE_TEMPLATE.format(attr=re.escape(attr)), re.IGNORECASE
    )
    return pattern.subn(lambda m: f"{m.group(1)}{value}{m.group(3)}", tag, count=1)


def touch_updated_at(text: str, timestamp: str) -> tuple[str, dict]:
    meta_count = 0
    body_count = 0

    def meta_repl(match: re.Match) -> str:
        nonlocal meta_count
        tag, count = replace_attr(match.group(0), "content", timestamp)
        meta_count += count
        return tag

    text = UPDATED_META_RE.sub(meta_repl, text, count=1)

    body_match = BODY_OPEN_RE.search(text)
    if body_match:
        tag, count = replace_attr(body_match.group(0), "data-updated-at", timestamp)
        body_count += count
        text = text[: body_match.start()] + tag + text[body_match.end() :]

    return text, {
        "meta_updated_at": meta_count,
        "body_data_updated_at": body_count,
        "updated_at": timestamp,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_html", help="Existing index.html to update")
    parser.add_argument("--body-file", help="HTML fragment to place inside <body>")
    parser.add_argument(
        "--touch-updated-at",
        action="store_true",
        help="Refresh known moodboard updated-at fields after replacing body",
    )
    parser.add_argument(
        "--project-dir",
        help="Project directory used to normalize local image references",
    )
    parser.add_argument(
        "--no-process-images",
        action="store_true",
        help="Do not normalize local image references before writing body",
    )
    parser.add_argument(
        "--local-image-mode",
        choices=["symlink", "copy"],
        default="symlink",
        help="How local absolute/file image refs are materialized",
    )
    parser.add_argument(
        "--cache-dir",
        default="assets/references",
        help="Project-relative directory for materialized images",
    )
    args = parser.parse_args(argv)

    index_path = Path(args.index_html).expanduser()
    if not index_path.exists():
        print(
            json.dumps(
                {"ok": False, "error": "missing_index", "index_html": str(index_path)}
            )
        )
        return 2

    source = index_path.read_text(encoding="utf-8")
    head_end = HEAD_END_RE.search(source)
    search_start = head_end.end() if head_end else 0
    match = BODY_RE.search(source, search_start)
    if not match:
        print(
            json.dumps(
                {"ok": False, "error": "missing_body", "index_html": str(index_path)}
            )
        )
        return 2

    try:
        body = read_body(args)
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": "missing_body_content", "message": str(exc)}
            )
        )
        return 2
    image_processing = None
    if not args.no_process_images:
        project_dir = (
            Path(args.project_dir).expanduser().resolve()
            if args.project_dir
            else index_path.parent.resolve()
        )
        try:
            body, image_processing = process_image_sources(
                body, project_dir, args.local_image_mode, args.cache_dir
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "image_processing_failed",
                        "message": str(exc),
                        "index_html": str(index_path),
                    },
                    ensure_ascii=False,
                )
            )
            return 2

    replacement = f"{match.group(1)}\n{body.rstrip()}\n{match.group(3)}"
    updated = source[: match.start()] + replacement + source[match.end() :]
    touch_info = None
    updated_at = None
    touch_result = None
    if args.touch_updated_at:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        updated, touch_info = touch_updated_at(updated, timestamp)
        updated_at = touch_info["updated_at"]
        touch_result = {
            "meta_updated_at": bool(touch_info["meta_updated_at"]),
            "body_data_updated_at": bool(touch_info["body_data_updated_at"]),
        }

    index_path.write_text(updated, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "index_html": str(index_path),
                "preserved_prefix_chars": match.start(2),
                "preserved_suffix_chars": len(source) - match.end(2),
                "touch_updated_at": touch_info,
                "updated_at": updated_at,
                "touch_result": touch_result,
                "image_processing": image_processing,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
