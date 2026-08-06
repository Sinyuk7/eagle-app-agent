"""Semantic human output. Stdout remains available for machine data only."""

from __future__ import annotations

import sys
from typing import TextIO

from .ansi import plain_output

SYMBOLS = {
    "wait": "○",
    "active": "…",
    "success": "✓",
    "warning": "!",
    "failure": "×",
    "next": "→",
}
_COLORS = {
    "active": "36",
    "success": "32",
    "warning": "33",
    "failure": "31",
    "muted": "2",
}


class Printer:
    def __init__(
        self, *, stream: TextIO | None = None, plain: bool = False, quiet: int = 0
    ) -> None:
        self.stream = stream or sys.stderr
        self.plain = plain_output(self.stream, plain=plain)
        self.quiet = quiet

    def emit(self, text: str, *, state: str | None = None, force: bool = False) -> None:
        if self.quiet and not force and state != "failure":
            return
        prefix = f"{SYMBOLS[state]} " if state else ""
        rendered = prefix + text
        if state in _COLORS and not self.plain:
            rendered = f"\x1b[{_COLORS[state]}m{rendered}\x1b[0m"
        print(rendered, file=self.stream)

    def error(self, text: str) -> None:
        self.emit(text, state="failure", force=True)
