"""Optional yaspin adapter with line-oriented fallback."""

from __future__ import annotations

from contextlib import contextmanager

from .printer import Printer


@contextmanager
def spinner(printer: Printer, text: str):
    spin = None
    if not printer.plain:
        try:
            from yaspin import yaspin

            spin = yaspin(text=text, color="cyan", stream=printer.stream)
            spin.start()
        except ImportError:
            spin = None
    if spin is None:
        printer.emit(text, state="active")
    try:
        yield
    except Exception:
        if spin is not None:
            spin.fail("×")
        raise
    else:
        if spin is not None:
            spin.ok("✓")
