"""Known-total progress with an alive-progress adapter and readable fallback."""

from __future__ import annotations

import re
import unicodedata
from collections import deque

from .printer import Printer

_ITEM_TITLE_WIDTH = 36


def _cell_width(text: str) -> int:
    width = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def _fit_title(text: str, width: int = _ITEM_TITLE_WIDTH) -> str:
    """Fit a title to terminal cells, preserving room for an ASCII ellipsis."""
    if re.fullmatch(r"[0-9a-fA-F]{32}", text):
        text = text[:8] + "..."
    if _cell_width(text) <= width:
        return text + " " * (width - _cell_width(text))

    limit = max(width - 3, 0)
    rendered: list[str] = []
    used = 0
    for character in text:
        character_width = _cell_width(character)
        if used + character_width > limit:
            break
        rendered.append(character)
        used += character_width
    return "".join(rendered) + "..." + " " * (width - used - 3)


def _split_outcome(text: str) -> tuple[str, str]:
    title, separator, outcome = text.rpartition(": ")
    return (title, outcome) if separator else (text, "")


class Progress:
    def __init__(self, printer: Printer, total: int, label: str) -> None:
        self.printer, self.total, self.label = printer, total, label
        self.count = 0
        self.recent: deque[str] = deque(maxlen=1)
        self._bar = None
        self._update = None

    def __enter__(self) -> Progress:
        if not self.printer.plain:
            try:
                from alive_progress import alive_bar

                self._bar = alive_bar(
                    self.total,
                    title=self.label,
                    file=self.printer.stream,
                    # Make the throughput unit explicit: this is completed
                    # images per second, not per-request API latency.
                    stats="(~{eta}, {rate:.1f} images/s)",
                )
                self._update = self._bar.__enter__()
            except ImportError:
                self._bar = None
                self._update = None
        if self._bar is None:
            self.printer.emit(f"{self.label}: 0/{self.total}", state="active")
        return self

    def update(self, text: str) -> None:
        self.count += 1
        title, outcome = _split_outcome(text)
        fitted = _fit_title(title)
        plain_text = f"{fitted.rstrip()} {outcome}".rstrip()
        live_text = f"{self.printer.style(fitted, 'subtle')} {outcome}".rstrip()
        self.recent.append(live_text if self._update is not None else plain_text)
        if self._update is not None:
            self._update.text = " | ".join(self.recent)
            self._update()
        elif self.printer.quiet == 0:
            self.printer.emit(
                f"{self.label}: {self.count}/{self.total} {plain_text}", state="active"
            )

    def __exit__(self, *_args: object) -> None:
        if self._bar is not None:
            self._bar.__exit__(*_args)
        self._update = None
