from __future__ import annotations

import argparse
import io
import json
import os
import time
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest import mock

import moodtag
from moodtag.cli import (
    Board,
    BoardScope,
    EagleItem,
    RunResult,
    TagItemResult,
    run_tag_analysis,
)
from moodtag.ui.menu import MenuCancelled, MenuChoice, choose
from moodtag.ui.printer import Printer
from moodtag.ui.session import Session


def item(index: int) -> EagleItem:
    return EagleItem(str(index), f"image-{index}", "jpg", [], [], "")


class Eagle:
    def __init__(self) -> None:
        self.updates: list[str] = []
        self.analysis_count = 0

    def app_info(self):
        return {}

    def update_item(self, item_id, **_kwargs):
        self.updates.append(item_id)


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class WorkflowTests(unittest.TestCase):
    def tag_args(self, *options: str):
        return moodtag.build_parser().parse_args(
            ["tag", "--board", "board", "--plain", *options]
        )

    def test_concurrent_analysis_yields_completion_order(self):
        def analyze(*, index, item, **_kwargs):
            time.sleep(0.03 if index == 1 else 0)
            return TagItemResult(index=index, item=item)

        with mock.patch("moodtag.cli.analyze_tag_item", side_effect=analyze):
            results = list(
                run_tag_analysis(
                    work_items=[(1, item(1)), (2, item(2))],
                    eagle=object(),
                    vision=object(),
                    taxonomy={},
                    image_edge=256,
                    retries=0,
                    max_tags=1,
                    concurrency=2,
                )
            )
        self.assertEqual([result.index for result in results], [2, 1])

    def test_tag_analyzes_all_before_writing_and_emits_json(self):
        eagle = Eagle()
        first, second = item(1), item(2)
        scope = BoardScope(Board("board", "Board", "Board"), [], [first, second])
        probe = TagItemResult(index=1, item=first, tags=["one"], annotation="one")
        result = TagItemResult(index=2, item=second, tags=["two"], annotation="two")
        stdout, stderr = io.StringIO(), io.StringIO()

        def update(item_id, **kwargs):
            self.assertEqual(eagle.analysis_count, 2)
            eagle.updates.append(item_id)

        eagle.update_item = update
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", side_effect=[probe]),
            mock.patch("moodtag.cli.run_tag_analysis", return_value=iter([result])),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            eagle.analysis_count = 2
            self.assertEqual(
                moodtag.cli._command_tag_v2(self.tag_args("--write", "--json")), 0
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changed"], 2)
        self.assertEqual(eagle.updates, ["1", "2"])
        self.assertNotIn("\x1b", stderr.getvalue())

    def test_concurrent_analysis_completes_before_stable_multi_item_writes(self):
        eagle = Eagle()
        items = [item(index) for index in range(1, 5)]
        scope = BoardScope(Board("board", "Board", "Board"), [], items)
        completed: list[int] = []

        def analyze(*, index, item, **_kwargs):
            if index == 2:
                time.sleep(0.03)
            completed.append(index)
            return TagItemResult(
                index=index,
                item=item,
                tags=[f"tag-{index}"],
                annotation=f"note-{index}",
            )

        def update(item_id, **_kwargs):
            self.assertEqual(set(completed), {1, 2, 3, 4})
            eagle.updates.append(item_id)

        eagle.update_item = update
        stdout = io.StringIO()
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", side_effect=analyze),
            redirect_stdout(stdout),
        ):
            self.assertEqual(
                moodtag.cli._command_tag_v2(
                    self.tag_args("--write", "--json", "--concurrency", "2")
                ),
                0,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changed"], 4)
        self.assertEqual(eagle.updates, ["1", "2", "3", "4"])

    def test_probe_failure_prevents_bulk_and_write(self):
        eagle = Eagle()
        scope = BoardScope(Board("board", "Board", "Board"), [], [item(1)])
        failed = TagItemResult(index=1, item=item(1), error=RuntimeError("bad model"))
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", return_value=failed),
            mock.patch("moodtag.cli.run_tag_analysis") as bulk,
        ):
            self.assertEqual(moodtag.cli._command_tag_v2(self.tag_args("--write")), 1)
        bulk.assert_not_called()
        self.assertEqual(eagle.updates, [])

    def test_cancellation_returns_130_without_writes(self):
        eagle = Eagle()
        scope = BoardScope(Board("board", "Board", "Board"), [], [item(1), item(2)])
        probe = TagItemResult(index=1, item=item(1), tags=["one"], annotation="one")
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", return_value=probe),
            mock.patch("moodtag.cli.run_tag_analysis", side_effect=KeyboardInterrupt),
        ):
            self.assertEqual(moodtag.cli._command_tag_v2(self.tag_args("--write")), 130)
        self.assertEqual(eagle.updates, [])

    def test_write_cancellation_reports_partial_updates_without_traceback(self):
        eagle = Eagle()
        first, second = item(1), item(2)
        scope = BoardScope(Board("board", "Board", "Board"), [], [first, second])
        probe = TagItemResult(index=1, item=first, tags=["one"], annotation="one")
        result = TagItemResult(index=2, item=second, tags=["two"], annotation="two")
        stdout, stderr = io.StringIO(), io.StringIO()

        def update(item_id, **_kwargs):
            if item_id == "2":
                raise KeyboardInterrupt
            eagle.updates.append(item_id)

        eagle.update_item = update
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", return_value=probe),
            mock.patch("moodtag.cli.run_tag_analysis", return_value=iter([result])),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(
                moodtag.cli._command_tag_v2(self.tag_args("--write", "--json")),
                130,
            )

        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["cancelled"])
        self.assertEqual(payload["changed"], 1)
        self.assertEqual(payload["exit_code"], 130)
        self.assertEqual(eagle.updates, ["1"])
        self.assertIn("Some images may already be updated.", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_quiet_and_plain_printer_never_emit_ansi(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            moodtag.cli.Printer(plain=True, quiet=1).emit("hidden", state="active")
            moodtag.cli.Printer(plain=True).emit("visible", state="success")
        self.assertEqual(stderr.getvalue(), "✓ visible\n")

    def test_printer_uses_semantic_tones_and_plain_fallbacks(self):
        capable = TtyStringIO()
        with mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            printer = Printer(stream=capable)
            printer.emit("Moodtag", tone="brand")
            printer.emit_parts([("Model: ", "secondary"), ("Ready", "success")])
            printer.emit("Working", state="active")
        rendered = capable.getvalue()
        self.assertIn("\x1b[38;5;208mMoodtag\x1b[0m", rendered)
        self.assertIn("\x1b[90mModel: \x1b[0m", rendered)
        self.assertIn("\x1b[32mReady\x1b[0m", rendered)
        self.assertIn("\x1b[36m… Working\x1b[0m", rendered)

        basic_color = TtyStringIO()
        with mock.patch.dict(os.environ, {"TERM": "xterm"}, clear=True):
            Printer(stream=basic_color).emit("Moodtag", tone="brand")
        self.assertEqual(basic_color.getvalue(), "\x1b[93mMoodtag\x1b[0m\n")

        fallback = TtyStringIO()
        with mock.patch.dict(
            os.environ, {"TERM": "xterm-256color", "NO_COLOR": "1"}, clear=True
        ):
            Printer(stream=fallback).emit("Moodtag", tone="brand")
        self.assertEqual(fallback.getvalue(), "Moodtag\n")

        dumb = TtyStringIO()
        with mock.patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            Printer(stream=dumb).emit("Moodtag", tone="brand")
        self.assertEqual(dumb.getvalue(), "Moodtag\n")
        non_tty = io.StringIO()
        Printer(stream=non_tty).emit("Moodtag", tone="brand")
        self.assertEqual(non_tty.getvalue(), "Moodtag\n")

    def test_menu_sections_keep_keys_and_plain_readability(self):
        stream = io.StringIO()
        printer = Printer(stream=stream, plain=True)
        with mock.patch("builtins.input", return_value="q"):
            with self.assertRaises(MenuCancelled):
                choose(
                    printer,
                    "Choose an action",
                    [
                        MenuChoice("Tag a board", primary=True),
                        MenuChoice("Change tagging style", section="Settings"),
                        MenuChoice("Model setup"),
                    ],
                )
        self.assertEqual(
            stream.getvalue(),
            "→ Choose an action\n"
            "1  Tag a board\n\n"
            "Settings\n"
            "2  Change tagging style\n"
            "3  Model setup\n"
            "q  Quit\n>\n",
        )

    def test_human_final_result_is_grouped_and_quiet_stays_compact(self):
        result = RunResult("Board", 4, 4, 2, 1, 1)
        stream = io.StringIO()
        args = argparse.Namespace(json=False, quiet=0, write=True)
        self.assertEqual(
            moodtag.cli._emit_final_result(
                Printer(stream=stream, plain=True), args, result
            ),
            1,
        )
        self.assertEqual(
            stream.getvalue(),
            "Complete\n\n✓ 2 updated\n! 1 skipped\n× 1 failed\n\n"
            "→ Use -v for image results\n",
        )

        quiet = io.StringIO()
        args = argparse.Namespace(json=False, quiet=1, write=True)
        self.assertEqual(
            moodtag.cli._emit_final_result(
                Printer(stream=quiet, plain=True, quiet=1), args, result
            ),
            1,
        )
        self.assertEqual(quiet.getvalue(), "Complete: 2 updated, 1 failed\n")

    def test_probe_starts_progress_at_one_of_full_selected_total(self):
        records: list[tuple[str, object]] = []

        class ProgressRecorder:
            def update(self, text):
                records.append(("update", text))

        class SessionRecorder:
            def __init__(self, _printer):
                pass

            @contextmanager
            def wait(self, text):
                records.append(("wait", text))
                yield

            @contextmanager
            def progress(self, total, label):
                records.append(("progress", (total, label)))
                yield ProgressRecorder()

        eagle = Eagle()
        first, second = item(1), item(2)
        scope = BoardScope(Board("board", "Board", "Board"), [], [first, second])
        probe = TagItemResult(index=1, item=first, tags=["one"], annotation="one")
        result = TagItemResult(index=2, item=second, tags=["two"], annotation="two")
        stdout = io.StringIO()
        with (
            mock.patch("moodtag.cli.Session", SessionRecorder),
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.cli.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
            mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
            mock.patch("moodtag.cli.analyze_tag_item", return_value=probe),
            mock.patch("moodtag.cli.run_tag_analysis", return_value=iter([result])),
            redirect_stdout(stdout),
        ):
            self.assertEqual(moodtag.cli._command_tag_v2(self.tag_args("--json")), 0)
        self.assertIn(("progress", (2, "Analyzing")), records)
        self.assertEqual(
            [value for kind, value in records if kind == "update"],
            ["image-1: ✓", "image-2: ✓"],
        )

    def test_guided_confirmation_clears_the_complete_region_before_tagging(self):
        @contextmanager
        def no_spinner(*_args, **_kwargs):
            yield

        scope = BoardScope(Board("board", "Board", "Board"), [], [item(1)])
        args = moodtag.build_parser().parse_args(
            ["tag", "--board", "board", "--mock-model", "--guided-main-flow"]
        )
        with (
            mock.patch("moodtag.cli.spinner", no_spinner),
            mock.patch("moodtag.cli.EagleClient", return_value=Eagle()),
            mock.patch("moodtag.cli._load_guided_board_scope", return_value=scope),
            mock.patch("moodtag.cli.prompt_yes_no", return_value=True),
            mock.patch("moodtag.cli.supports_cursor", return_value=True),
            mock.patch("moodtag.cli.clear_previous_lines") as clear_region,
            mock.patch("moodtag.cli._command_tag_v2", return_value=0) as command_tag,
        ):
            self.assertEqual(moodtag.cli._command_guided_tag_v2(args), 0)
        self.assertEqual(clear_region.call_args.args[1], 6)
        command_tag.assert_called_once_with(args)

    def test_menu_retries_then_returns_back_and_session_is_exclusive(self):
        stream = io.StringIO()
        printer = Printer(stream=stream, plain=True)
        with mock.patch("builtins.input", side_effect=["bad", "b"]):
            self.assertIsNone(choose(printer, "Choose", ["one"], allow_back=True))
        self.assertIn("Enter a valid option.", stream.getvalue())
        with mock.patch("builtins.input", return_value="q"):
            with self.assertRaises(MenuCancelled):
                choose(printer, "Choose", ["one"])
        session = Session(printer)
        with session.wait("Preparing"):
            with self.assertRaises(RuntimeError):
                with session.progress(1, "Analyzing"):
                    pass


if __name__ == "__main__":
    unittest.main()
