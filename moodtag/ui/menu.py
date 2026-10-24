"""Numbered menu helpers with safe cancellation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .printer import Printer


class MenuCancelled(Exception):
    pass


@dataclass(frozen=True)
class MenuChoice:
    label: str
    section: str | None = None
    primary: bool = False


def choose(
    printer: Printer,
    title: str,
    choices: Sequence[str | MenuChoice],
    *,
    allow_back: bool = False,
    default: int | None = None,
) -> int | None:
    normalized = [
        choice if isinstance(choice, MenuChoice) else MenuChoice(choice)
        for choice in choices
    ]
    printer.emit(title, state="next")
    section = None
    for index, choice in enumerate(normalized, start=1):
        if choice.section and choice.section != section:
            if index > 1:
                printer.emit("")
            printer.emit(choice.section, tone="secondary")
            section = choice.section
        key_tone = "accent" if choice.primary else "primary"
        printer.emit_parts([(f"{index}  ", key_tone), (choice.label, "primary")])
    if allow_back:
        printer.emit_parts([("b  ", "secondary"), ("Back", "secondary")])
    printer.emit_parts([("q  ", "subtle"), ("Quit", "subtle")])
    while True:
        try:
            printer.emit(">", tone="accent")
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise MenuCancelled from exc
        if answer == "q":
            raise MenuCancelled
        if allow_back and answer == "b":
            return None
        if not answer and default is not None:
            if 0 <= default < len(normalized):
                return default
        if answer.isdigit() and 1 <= int(answer) <= len(normalized):
            return int(answer) - 1
        printer.emit("Enter a valid option.", state="warning")
