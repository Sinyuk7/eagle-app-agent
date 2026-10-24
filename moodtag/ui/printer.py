"""Semantic human output. Stdout remains available for machine data only."""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Sequence
from typing import Literal, TextIO

from .ansi import plain_output, supports_256_color, terminal_width

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
        prefix_width = self._cell_width(prefix)
        text = self._fit(
            text, max_width=max(1, terminal_width(self.stream) - prefix_width)
        )
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
        fitted = self._fit("".join(text for text, _tone in parts))
        remaining = fitted
        rendered_parts: list[str] = []
        for text, tone in parts:
            if not remaining:
                break
            piece = remaining[: len(text)]
            rendered_parts.append(self.style(piece, tone))
            remaining = remaining[len(piece) :]
        print("".join(rendered_parts), file=self.stream)

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

    @staticmethod
    def _cell_width(text: str) -> int:
        width = 0
        for char in text:
            if unicodedata.combining(char) or unicodedata.category(char) in {
                "Cf",
                "Mn",
                "Me",
            }:
                continue
            width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        return width

    def _fit(self, text: str, *, max_width: int | None = None) -> str:
        width = (
            max_width if max_width is not None else max(1, terminal_width(self.stream))
        )
        visible = 0
        result: list[str] = []
        for char in text:
            if unicodedata.combining(char) or unicodedata.category(char) in {
                "Cf",
                "Mn",
                "Me",
            }:
                result.append(char)
                continue
            char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
            if visible + char_width > width:
                if width >= 1:
                    result.append("…")
                break
            result.append(char)
            visible += char_width
        return "".join(result)

    def error(self, text: str) -> None:
        self.emit(text, state="failure", force=True)

    def emit_hyperlink(self, label: str, url: str) -> None:
        """Render an OSC 8 link on interactive terminals, or a copyable URL."""
        if self.quiet:
            return
        if self.plain:
            self.emit(f"{label}: {url}")
            return
        # Fit only visible text: truncating the OSC 8 sequence can leave the
        # terminal in hyperlink mode for everything printed afterwards.
        visible_label = self._fit(label)
        print(
            f"\x1b]8;;{url}\x1b\\{self.style(visible_label, 'accent')}\x1b]8;;\x1b\\",
            file=self.stream,
        )
