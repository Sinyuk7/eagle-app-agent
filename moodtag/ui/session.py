"""Own terminal renderer lifecycle for one Moodtag command."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .printer import Printer
from .progress import Progress
from .spinner import spinner


class Session:
    def __init__(self, printer: Printer) -> None:
        self.printer = printer
        self._active = False

    @contextmanager
    def wait(self, text: str) -> Iterator[None]:
        if self._active:
            raise RuntimeError("terminal renderer already active")
        self._active = True
        try:
            with spinner(self.printer, text):
                yield
        finally:
            self._active = False

    @contextmanager
    def progress(self, total: int, label: str) -> Iterator[Progress]:
        if self._active:
            raise RuntimeError("terminal renderer already active")
        self._active = True
        try:
            with Progress(self.printer, total, label) as renderer:
                yield renderer
        finally:
            self._active = False
