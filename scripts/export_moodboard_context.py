#!/usr/bin/env python3
"""Export an Eagle moodboard folder as compact Markdown context."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import moodtag  # noqa: E402
from moodtag_core.annotation import ANNOTATION_LABEL_ORDER, parse_annotation_fields  # noqa: E402


def build_context_markdown(
    board: moodtag.Board,
    items: list[moodtag.EagleItem],
    *,
    include_pending: bool = False,
) -> str:
    rows: list[tuple[moodtag.EagleItem, dict[str, str], bool]] = []
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="export_moodboard_context")
    parser.add_argument("--board", required=True, help="Eagle folder id, name, or path")
    parser.add_argument(
        "--eagle-api",
        default=os.environ.get("MOODTAG_EAGLE_API", moodtag.DEFAULT_EAGLE_API),
    )
    parser.add_argument("--output", default="", help="Write Markdown to this file")
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Include items without complete Moodtag annotation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        moodtag.load_env_defaults()
        args = parse_args(argv)
        eagle = moodtag.EagleClient(args.eagle_api)
        eagle.app_info()
        board = moodtag.resolve_board(args.board, eagle.boards())
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
    except moodtag.MoodtagError as exc:
        print(f"error: {moodtag.redact(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
