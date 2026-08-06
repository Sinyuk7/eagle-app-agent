"""Semantic human output. Stdout remains available for machine data only."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Literal, TextIO

from .ansi import plain_output, supports_256_color

SYMBOLS = {
    "wait": "○",
    "active": "…",
    "success": "✓",
    "warning": "!",
    "failure": "×",
    "next": "→",
}
Tone = Literal[
    "brand",
    "accent",
    "primary",
    "secondary",
    "subtle",
    "success",
    "warning",
    "failure",
    "active",
    "next",
    "wait",
]

_STATE_COLORS = {
    "active": "36",
    "success": "32",
    "warning": "33",
    "failure": "31",
}
_STATIC_COLORS = {
    "primary": "97",
    "secondary": "90",
    "subtle": "2",
}


class Printer:
    def __init__(
        self, *, stream: TextIO | None = None, plain: bool = False, quiet: int = 0
    ) -> None:
        self.stream = stream or sys.stderr
        self.plain = plain_output(self.stream, plain=plain)
        self.quiet = quiet

    def emit(
        self,
        text: str,
        *,
        state: str | None = None,
        tone: Tone | None = None,
        force: bool = False,
    ) -> None:
        if self.quiet and not force and state != "failure":
            return
        prefix = f"{SYMBOLS[state]} " if state else ""
        rendered = prefix + self.style(text, state or tone)
        if state and not self.plain:
            rendered = self.style(prefix + text, state)
        print(rendered, file=self.stream)

    def emit_parts(
        self,
        parts: Sequence[tuple[str, Tone]],
        *,
        force: bool = False,
    ) -> None:
        if self.quiet and not force:
            return
        print("".join(self.style(text, tone) for text, tone in parts), file=self.stream)

    def style(self, text: str, tone: Tone | None) -> str:
        if self.plain or tone is None:
            return text
        code = self._color_code(tone)
        return f"\x1b[{code}m{text}\x1b[0m" if code else text

    def _color_code(self, tone: Tone) -> str:
        if tone in {"brand", "accent"}:
            return "38;5;208" if supports_256_color(self.stream) else "93"
        if tone == "next":
            return "38;5;208" if supports_256_color(self.stream) else "93"
        if tone == "wait":
            return _STATE_COLORS["active"]
        return _STATE_COLORS.get(tone) or _STATIC_COLORS.get(tone, "")

    def error(self, text: str) -> None:
        self.emit(text, state="failure", force=True)
