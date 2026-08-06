"""Numbered menu helpers with safe cancellation."""

from __future__ import annotations

from collections.abc import Sequence

from .printer import Printer


class MenuCancelled(Exception):
    pass


def choose(
    printer: Printer, title: str, choices: Sequence[str], *, allow_back: bool = False
) -> int | None:
    printer.emit(title, state="next")
    for index, choice in enumerate(choices, start=1):
        printer.emit(f"{index}. {choice}")
    if allow_back:
        printer.emit("b. Back")
    printer.emit("q. Quit")
    while True:
        try:
            printer.emit(">")
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise MenuCancelled from exc
        if answer == "q":
            raise MenuCancelled
        if allow_back and answer == "b":
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return int(answer) - 1
        printer.emit("Enter a valid option.", state="warning")
