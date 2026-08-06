"""Known-total progress with an alive-progress adapter and readable fallback."""

from __future__ import annotations

from collections import deque

from .printer import Printer


class Progress:
    def __init__(self, printer: Printer, total: int, label: str) -> None:
        self.printer, self.total, self.label = printer, total, label
        self.count = 0
        self.recent: deque[str] = deque(maxlen=3)
        self._bar = None

    def __enter__(self) -> Progress:
        if not self.printer.plain:
            try:
                from alive_progress import alive_bar

                self._bar = alive_bar(
                    self.total, title=self.label, file=self.printer.stream
                )
                self._bar.__enter__()
            except ImportError:
                self._bar = None
        if self._bar is None:
            self.printer.emit(f"{self.label}: 0/{self.total}", state="active")
        return self

    def update(self, text: str) -> None:
        self.count += 1
        self.recent.append(text)
        if self._bar is not None:
            self._bar(text=" | ".join(self.recent))
        elif self.printer.quiet == 0:
            self.printer.emit(
                f"{self.label}: {self.count}/{self.total} {text}", state="active"
            )

    def __exit__(self, *_args: object) -> None:
        if self._bar is not None:
            self._bar.__exit__(*_args)
