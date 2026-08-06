"""Small terminal capability helpers."""

from __future__ import annotations

import os
import shutil
from typing import TextIO


def is_tty(stream: TextIO) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)())


def plain_output(stream: TextIO, *, plain: bool = False) -> bool:
    return (
        plain
        or not is_tty(stream)
        or bool(os.environ.get("NO_COLOR"))
        or os.environ.get("TERM") == "dumb"
    )


def supports_cursor(stream: TextIO, *, plain: bool = False) -> bool:
    return not plain_output(stream, plain=plain)


def supports_256_color(stream: TextIO) -> bool:
    """Return whether a color-capable terminal advertises 256-color support."""
    if not is_tty(stream):
        return False
    term = os.environ.get("TERM", "")
    color_term = os.environ.get("COLORTERM", "").lower()
    return "256color" in term or color_term in {"truecolor", "24bit"}


def terminal_width(stream: TextIO) -> int:
    del stream
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def clear_line(stream: TextIO) -> None:
    stream.write("\r\x1b[2K")


def move_cursor_up(stream: TextIO, lines: int = 1) -> None:
    if lines > 0:
        stream.write(f"\x1b[{lines}A")


def clear_previous_lines(stream: TextIO, lines: int) -> None:
    """Clear the current line and a fixed number of preceding rendered lines."""
    for index in range(max(lines, 0)):
        clear_line(stream)
        if index + 1 < lines:
            move_cursor_up(stream)
