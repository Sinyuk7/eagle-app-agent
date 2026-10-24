"""Numbered menu helpers with safe cancellation."""

from __future__ import annotations

import builtins
import os
import select
import sys
import termios
from collections.abc import Sequence
from dataclasses import dataclass

from .locale import tr
from .printer import Printer

_ORIGINAL_INPUT = builtins.input


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
    if _supports_key_input(printer):
        return _choose_keys(
            printer, title, normalized, allow_back=allow_back, default=default
        )
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
        printer.emit_parts([("b  ", "secondary"), (tr("Back", "返回"), "secondary")])
    printer.emit_parts([("q  ", "subtle"), (tr("Quit", "退出"), "subtle")])
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
        printer.emit(tr("Enter a valid option.", "请输入有效选项。"), state="warning")


def _supports_key_input(printer: Printer) -> bool:
    if (
        builtins.input is not _ORIGINAL_INPUT
        or printer.plain
        or not sys.stdin.isatty()
        or not getattr(printer.stream, "isatty", lambda: False)()
    ):
        return False
    try:
        termios.tcgetattr(sys.stdin.fileno())
    except (OSError, ValueError, termios.error):
        return False
    return True


def _choose_keys(
    printer: Printer,
    title: str,
    choices: Sequence[MenuChoice],
    *,
    allow_back: bool,
    default: int | None,
) -> int | None:
    selected = default if default is not None else 0
    rendered_section = None
    section_lines = 0
    for choice in choices:
        if choice.section and choice.section != rendered_section:
            section_lines += 1
            rendered_section = choice.section
    # The renderer emits one physical line per title, section, choice and help
    # line. Keep this in sync with render() so cursor clearing starts exactly
    # at the top even when a section appears more than once.
    line_count = 2 + len(choices) + section_lines
    stream = printer.stream

    def render() -> None:
        printer.emit(title, state="next")
        section = None
        for index, choice in enumerate(choices):
            if choice.section and choice.section != section:
                printer.emit(choice.section, tone="secondary")
                section = choice.section
            if index == selected:
                label = f"❯ {choice.label}"
                if not printer.plain:
                    label = f"\x1b[1m{label}\x1b[0m"
                printer.emit(label, tone="accent")
            else:
                printer.emit(f"  {choice.label}")
        help_text = tr("↑↓ Move · Enter Select", "↑↓ 切换 · Enter 确认")
        if allow_back:
            help_text += " · " + tr("Esc/b Back", "Esc/b 返回")
        help_text += " · " + tr("q Quit", "q 退出")
        printer.emit(help_text, tone="subtle")
        stream.flush()

    def read_key() -> str:
        fd = sys.stdin.fileno()
        char = os.read(fd, 1).decode("utf-8", errors="ignore")
        if char == "\x1b":
            ready, _, _ = select.select([sys.stdin], [], [], 0.04)
            if ready:
                suffix = os.read(fd, 2).decode("ascii", errors="ignore")
                return (
                    "up" if suffix == "[A" else "down" if suffix == "[B" else "escape"
                )
            return "escape"
        if char in {"\r", "\n"}:
            return "enter"
        return char.lower()

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    interactive = list(previous)
    interactive[1] |= termios.OPOST
    interactive[3] &= ~(termios.ICANON | termios.ECHO)
    interactive[6] = list(previous[6])
    interactive[6][termios.VMIN] = 1
    interactive[6][termios.VTIME] = 0
    # Keep OPOST enabled. stdin and stderr usually share the same PTY, and
    # disabling output processing makes each printed newline retain its column.
    termios.tcsetattr(fd, termios.TCSADRAIN, interactive)
    try:
        render()
        while True:
            try:
                key = read_key()
            except (EOFError, KeyboardInterrupt) as exc:
                raise MenuCancelled from exc
            if key in {"q", "\x03"}:
                raise MenuCancelled
            if key == "enter":
                return selected
            if key.isdigit() and 1 <= int(key) <= len(choices):
                return int(key) - 1
            if allow_back and (key in {"b", "escape"}):
                return None
            if key == "up":
                selected = (selected - 1) % len(choices)
            elif key == "down":
                selected = (selected + 1) % len(choices)
            else:
                continue

            stream.write(f"\x1b[{line_count}A")
            for index in range(line_count):
                stream.write("\r\x1b[2K")
                if index + 1 < line_count:
                    stream.write("\x1b[1B")
            stream.write(f"\x1b[{line_count - 1}A\r")
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
