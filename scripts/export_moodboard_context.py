#!/usr/bin/env python3
"""Compatibility wrapper for `moodtag export-context`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moodtag.cli import main as moodtag_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return moodtag_main(["export-context", *(argv or sys.argv[1:])])


if __name__ == "__main__":
    raise SystemExit(main())
