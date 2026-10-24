from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import tempfile
import termios
import time
import types
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import moodtag
from moodtag.cli import (
    Board,
    BoardScope,
    EagleClient,
    EagleItem,
    MoodtagError,
    RunResult,
    ScopeInput,
    TagItemResult,
    choose_filters,
    resolve_item_scope,
    run_tag_analysis,
    unsupported_media_reason,
)
from moodtag.ui.menu import MenuCancelled, MenuChoice, choose
from moodtag.ui.printer import Printer
from moodtag.ui.progress import Progress, _cell_width, _fit_title
from moodtag_core.annotation import build_annotation_block
from moodtag_core.contract import MoodtagAnalysis
from moodtag_core.provider import OllamaVisionClient


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

    def test_selected_scope_has_a_direct_cli_entry(self):
        seen = []
        with mock.patch(
            "moodtag.cli.command_tag", side_effect=lambda args: seen.append(args) or 0
        ):
            self.assertEqual(moodtag.main(["selected", "--write"]), 0)
        self.assertTrue(seen[0].selected)
        self.assertTrue(seen[0].write)

    def test_selected_scope_is_a_fixed_snapshot_and_tag_filters_intersect(self):
        selected = [
            EagleItem("b", "b.jpg", "jpg", ["CELINE", "editorial"], [], ""),
            EagleItem("a", "a.jpg", "jpg", ["CELINE"], [], ""),
        ]
        eagle = mock.Mock()
        eagle.list_items.return_value = selected
        eagle.list_items.return_value.append(selected[0])
        resolved = resolve_item_scope(
            eagle,
            ScopeInput(selected=True, tags=("CELINE", "editorial")),
        )
        self.assertEqual([entry.id for entry in resolved.items], ["b"])
        self.assertEqual(eagle.list_items.call_count, 1)
        self.assertEqual(eagle.list_items.call_args.kwargs, {"selected": True})

    def test_selected_scope_reports_unsupported_eagle_filter(self):
        with mock.patch("moodtag.cli.http_request", return_value={"status": "error"}):
            with self.assertRaisesRegex(MoodtagError, "could not apply the requested"):
                EagleClient().list_items("", selected=True)

    def test_scope_tag_filter_intersects_and_accepts_manual_non_taxonomy_tag(self):
        eagle = mock.Mock()
        eagle.boards.return_value = [Board("folder", "Folder", "Folder")]
        eagle.list_items.return_value = [
            EagleItem("1", "one.jpg", "jpg", ["CELINE", "editorial"], [], ""),
            EagleItem("2", "two.jpg", "jpg", ["CELINE"], [], ""),
        ]
        with mock.patch("moodtag.cli.load_board_scope") as load_scope:
            load_scope.return_value = BoardScope(
                Board("folder", "Folder", "Folder"), [], eagle.list_items.return_value
            )
            result = resolve_item_scope(
                eagle, ScopeInput(folder="folder", tags=("CELINE", "editorial"))
            )
        self.assertEqual([entry.id for entry in result.items], ["1"])

    def test_unsupported_media_remains_in_snapshot_for_existing_skip_policy(self):
        candidate = EagleItem("1", "movie.mov", "mov", [], [], "")
        self.assertTrue(unsupported_media_reason(candidate))

    def test_v2_item_query_reads_all_pages_past_one_thousand(self):
        calls: list[int] = []

        def request(_method, _url, *, json_body, **_kwargs):
            offset = json_body["offset"]
            calls.append(offset)
            count = min(1000, 1001 - offset)
            rows = [
                {"id": str(index), "name": f"item-{index}.jpg", "ext": "jpg"}
                for index in range(offset, offset + count)
            ]
            return {
                "status": "success",
                "data": {
                    "data": rows,
                    "total": 1001,
                    "limit": 1000,
                    "offset": offset,
                },
            }

        with mock.patch("moodtag.cli.http_request", side_effect=request):
            items = EagleClient().list_items("folder")
        self.assertEqual(len(items), 1001)
        self.assertEqual(calls, [0, 1000])

    def test_rating_and_shape_use_native_v2_fields_and_map_star_metadata(self):
        requests = []

        def request(_method, _url, *, json_body, **_kwargs):
            requests.append(json_body)
            return {
                "status": "success",
                "data": {
                    "data": [{"id": "1", "star": 4, "width": 600, "height": 900}],
                    "total": 1,
                    "limit": 1000,
                    "offset": 0,
                },
            }

        with mock.patch("moodtag.cli.http_request", side_effect=request):
            items = EagleClient().list_items("folder", rating=4, shape="portrait")
        self.assertEqual(requests[0]["rating"], 4)
        self.assertEqual(requests[0]["shape"], "portrait")
        self.assertEqual(items[0].rating, 4)

    def test_rating_scope_validation_rejects_out_of_range_values(self):
        with self.assertRaisesRegex(MoodtagError, "between 0 and 5"):
            EagleClient().list_items("folder", rating=99)

    def test_entire_library_filters_ask_only_for_selected_conditions(self):
        printer = Printer(stream=io.StringIO(), plain=True)
        answers = iter(["1,2,3", "CELINE, editorial", "4", "panoramic-portrait"])
        with mock.patch("builtins.input", side_effect=lambda: next(answers)):
            self.assertEqual(
                choose_filters(printer),
                (["CELINE", "editorial"], 4, "panoramic-portrait"),
            )
        self.assertIn("Enter to skip · e.g. 1,2", printer.stream.getvalue())

    def test_empty_filter_selection_skips_all_filter_prompts(self):
        printer = Printer(stream=io.StringIO(), plain=True)
        with mock.patch("builtins.input", return_value="") as input_mock:
            self.assertEqual(choose_filters(printer), ([], None, ""))
        input_mock.assert_called_once()

    def test_filter_only_cli_infers_entire_library_scope(self):
        args = self.tag_args("--tag", "CELINE", "--rating", "4")
        args.board = ""
        moodtag.cli.validate_tag_args(args)
        self.assertTrue(args.library)

    def test_empty_resolved_scope_does_not_construct_model(self):
        args = self.tag_args("--json")
        eagle = Eagle()
        scope = BoardScope(Board("board", "Board", "Board"), [], [])
        with (
            mock.patch("moodtag.cli.public_attr", return_value=lambda _api: eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("moodtag.cli.make_vision_client") as make_vision,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(moodtag.cli._command_tag_v2(args), 0)
        make_vision.assert_not_called()

    def test_guided_selection_passes_the_resolved_snapshot_to_analysis(self):
        selected = item(1)
        eagle = Eagle()
        eagle.list_items = mock.Mock(return_value=[selected])
        args = moodtag.build_parser().parse_args(["tag", "--selected", "--mock-model"])
        args._interactive_home = True
        observed = []
        with (
            mock.patch("moodtag.cli.public_attr", return_value=lambda _api: eagle),
            mock.patch("moodtag.cli.prompt_yes_no", return_value=True),
            mock.patch(
                "moodtag.cli._command_tag_v2",
                side_effect=lambda forwarded: (
                    observed.append(forwarded._resolved_scope) or 0
                ),
            ),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(moodtag.cli._command_guided_tag_v2(args), 0)
        self.assertEqual(eagle.list_items.call_count, 1)
        self.assertEqual(observed[0].items, [selected])

    def test_guided_empty_scope_returns_to_scope_selection_without_model(self):
        eagle = Eagle()
        eagle.list_items = mock.Mock(return_value=[])
        args = moodtag.build_parser().parse_args(["tag", "--selected"])
        args._interactive_home = True
        with (
            mock.patch("moodtag.cli.public_attr", return_value=lambda _api: eagle),
            mock.patch("moodtag.cli.make_vision_client") as make_vision,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(moodtag.cli._command_guided_tag_v2(args), 3)
        make_vision.assert_not_called()

    def test_scope_menu_current_selection_does_not_ask_for_filters(self):
        seen = []
        with (
            mock.patch("moodtag.cli.choose", return_value=1),
            mock.patch(
                "moodtag.cli._command_guided_tag_v2",
                side_effect=lambda args: seen.append(args) or 0,
            ),
        ):
            self.assertEqual(
                moodtag.cli.command_guided_scope_flow(
                    Printer(stream=io.StringIO(), plain=True)
                ),
                0,
            )
        self.assertTrue(seen[0].selected)
        self.assertFalse(seen[0].library)

    def test_scope_menu_folder_does_not_ask_for_filters(self):
        seen = []
        with (
            mock.patch("moodtag.cli.choose", return_value=0),
            mock.patch("builtins.input", return_value="folder-id"),
            mock.patch(
                "moodtag.cli._command_guided_tag_v2",
                side_effect=lambda args: seen.append(args) or 0,
            ),
        ):
            self.assertEqual(
                moodtag.cli.command_guided_scope_flow(
                    Printer(stream=io.StringIO(), plain=True)
                ),
                0,
            )
        self.assertEqual(seen[0].board, "folder-id")
        self.assertFalse(seen[0].library)
        self.assertEqual(seen[0].tags, [])

    def test_entire_library_scope_fails_closed_when_over_limit(self):
        eagle = mock.Mock()
        eagle.list_items.return_value = [item(1), item(2)]
        with self.assertRaisesRegex(MoodtagError, "Add filters"):
            resolve_item_scope(eagle, ScopeInput(library=True, max_items=1))

    def test_entire_library_count_guard_runs_before_item_download(self):
        eagle = mock.Mock()
        eagle.count_items.return_value = 25_840
        with self.assertRaisesRegex(MoodtagError, "25,840"):
            resolve_item_scope(eagle, ScopeInput(library=True, max_items=9_999))
        eagle.list_items.assert_not_called()

    def test_entire_library_count_guard_allows_filtered_count(self):
        eagle = mock.Mock()
        eagle.count_items.return_value = 25_840
        eagle.list_items.return_value = [
            EagleItem("1", "image-1", "jpg", ["editorial"], [], "")
        ]
        result = resolve_item_scope(
            eagle, ScopeInput(library=True, tags=("editorial",), max_items=9_999)
        )
        self.assertEqual(len(result.items), 1)
        eagle.list_items.assert_called_once()

    def test_library_tag_filter_stops_pagination_after_match_limit(self):
        calls = []

        def request(_method, _url, *, json_body, **_kwargs):
            offset = json_body["offset"]
            calls.append((json_body["limit"], offset))
            rows = [
                {
                    "id": str(offset + index),
                    "name": f"item-{offset + index}.jpg",
                    "ext": "jpg",
                    "tags": ["keep"] if offset >= 6 else ["other"],
                }
                for index in range(3)
            ]
            return {
                "status": "success",
                "data": {"data": rows, "total": 9, "limit": 3, "offset": offset},
            }

        eagle = EagleClient()
        with mock.patch("moodtag.cli.http_request", side_effect=request):
            with self.assertRaisesRegex(MoodtagError, "--max-board-items 2"):
                resolve_item_scope(
                    eagle,
                    ScopeInput(library=True, tags=("keep",), max_items=2),
                )
        self.assertEqual(calls, [(1, 0), (1000, 0), (1000, 3), (1000, 6)])

    def test_export_context_writes_expected_markdown(self):
        complete = EagleItem(
            "1",
            "portrait.jpg",
            "jpg",
            ["portrait", "editorial"],
            [],
            build_annotation_block(
                MoodtagAnalysis(
                    brief="A red portrait",
                    elements=["person"],
                    use="editorial",
                    key="red light",
                    camera="close-up",
                    light_color="red",
                )
            ),
            width=1200,
            height=1600,
            size=2048,
            palettes=[{"color": [255, 0, 0], "ratio": 25}],
        )
        pending = EagleItem("2", "pending.jpg", "jpg", [], [], "")
        scope = BoardScope(
            Board("board", "Board", "Studio/Board"), [], [complete, pending]
        )
        eagle = Eagle()
        eagle.library_info = lambda: {}
        stdout = io.StringIO()

        with (
            mock.patch("moodtag.cli.public_attr", return_value=lambda _api: eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            redirect_stdout(stdout),
        ):
            args = moodtag.build_parser().parse_args(
                ["export-context", "--board", "board"]
            )
            self.assertEqual(moodtag.cli.command_export_context(args), 0)

        markdown = stdout.getvalue()
        self.assertIn("# Moodboard Context: Studio/Board", markdown)
        self.assertIn("Items: 2", markdown)
        self.assertIn("Exported: 1", markdown)
        self.assertIn("Pending skipped: 1", markdown)
        self.assertIn("A red portrait.jpg", markdown)
        self.assertIn("Tags: portrait | editorial", markdown)
        self.assertIn("Palette: #ff0000 25%", markdown)
        self.assertNotIn("pending.jpg", markdown)

    def test_export_context_output_option_writes_markdown_file(self):
        complete = EagleItem(
            "1",
            "portrait.jpg",
            "jpg",
            [],
            [],
            build_annotation_block(
                MoodtagAnalysis(
                    brief="A quiet portrait",
                    elements=["person"],
                    use="editorial",
                    key="stillness",
                    camera="eye level",
                    light_color="soft light",
                )
            ),
        )
        scope = BoardScope(Board("board", "Board", "Board"), [], [complete])
        eagle = Eagle()
        eagle.library_info = lambda: {}

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch("moodtag.cli.public_attr", return_value=lambda _api: eagle),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
        ):
            output_path = Path(tmp) / "context.md"
            args = moodtag.build_parser().parse_args(
                ["export-context", "--board", "board", "--output", str(output_path)]
            )
            self.assertEqual(moodtag.cli.command_export_context(args), 0)
            self.assertTrue(output_path.exists())
            self.assertIn("# Moodboard Context: Board", output_path.read_text())
            self.assertIn("A quiet portrait.jpg", output_path.read_text())

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

    def test_ollama_cold_start_resumes_guided_tag_job(self):
        """A cold local API is launched once, then the requested job proceeds."""
        events: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path != "/api/version":
                    self.send_error(404)
                    return
                encoded = b'{"version":"test-ollama"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server: ThreadingHTTPServer | None = None

        def launch_ollama(*_args, **_kwargs):
            nonlocal server
            events.append("launch")
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            import threading

            threading.Thread(target=server.serve_forever, daemon=True).start()
            return types.SimpleNamespace(returncode=0)

        first = item(1)
        scope = BoardScope(Board("board", "Board", "Board"), [], [first])
        result = TagItemResult(index=1, item=first, tags=["one"], annotation="one")
        eagle = Eagle()
        eagle.app_info = lambda: events.append("eagle") or {}
        eagle.update_item = lambda *_args, **_kwargs: None
        client = OllamaVisionClient(
            base_url=f"http://127.0.0.1:{port}", model="vision:latest", preset="smoke"
        )
        stdout = io.StringIO()

        def analyze(**_kwargs):
            events.append("analyze")
            return result

        try:
            with (
                mock.patch("moodtag.make_vision_client", return_value=client),
                mock.patch("moodtag.EagleClient", return_value=eagle),
                mock.patch("moodtag.cli.load_board_scope", return_value=scope),
                mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
                mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
                mock.patch("moodtag.cli.analyze_tag_item", side_effect=analyze),
                mock.patch("moodtag_core.provider.sys.platform", "darwin"),
                mock.patch(
                    "moodtag_core.provider.subprocess.run", side_effect=launch_ollama
                ),
                redirect_stdout(stdout),
            ):
                self.assertEqual(
                    moodtag.cli._command_tag_v2(self.tag_args("--json")), 0
                )
            self.assertEqual(events, ["eagle", "launch", "analyze"])
            self.assertEqual(client.runtime["version"], "test-ollama")
            self.assertIn('"changed": 1', stdout.getvalue())
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()

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

    def test_printer_hyperlink_uses_osc8_or_copyable_plain_url(self):
        url = "https://example.test/register?aff=code"
        capable = TtyStringIO()
        with mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            Printer(stream=capable).emit_hyperlink("Recommended service ↗", url)
        self.assertIn(
            "\x1b]8;;https://example.test/register?aff=code\x1b\\", capable.getvalue()
        )
        self.assertIn("Recommended service ↗", capable.getvalue())

        plain = io.StringIO()
        Printer(stream=plain).emit_hyperlink("Recommended service ↗", url)
        self.assertEqual(plain.getvalue(), f"Recommended service ↗: {url}\n")

    def test_printer_hyperlink_truncation_keeps_osc8_closed(self):
        stream = TtyStringIO()
        with (
            mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True),
            mock.patch("moodtag.ui.printer.terminal_width", return_value=12),
        ):
            printer = Printer(stream=stream)
            printer.emit_hyperlink("A very long recommendation", "https://example.test")
            printer.emit("After link")
        output = stream.getvalue()
        self.assertEqual(output.count("\x1b]8;;"), 2)
        self.assertIn("\x1b]8;;\x1b\\", output)
        self.assertTrue(output.endswith("After link\n"))

    def test_final_result_uses_chinese_status_resources(self):
        output = io.StringIO()
        args = argparse.Namespace(json=False, quiet=0, write=True)
        with (
            mock.patch.dict(os.environ, {"MOODTAG_LANG": "zh"}),
            redirect_stderr(output),
        ):
            moodtag.cli._emit_final_result(
                Printer(stream=output), args, RunResult("folder", 3, 2, 2, 1, 0)
            )
        rendered = output.getvalue()
        self.assertIn("处理完成", rendered)
        self.assertIn("2 项已更新", rendered)
        self.assertIn("跳过 1 项", rendered)
        self.assertIn("失败 0 项", rendered)

    def test_menu_sections_keep_keys_and_plain_readability(self):
        stream = io.StringIO()
        printer = Printer(stream=stream, plain=True)
        with (
            mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}),
            mock.patch("builtins.input", return_value="q"),
        ):
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

    def test_tty_progress_calls_alive_bar_enter_handle(self):
        updates: list[tuple[str, int]] = []

        class BarHandle:
            text = ""

            def __call__(self, count=1):
                updates.append((self.text, count))

        class BarContext:
            exited = False

            def __enter__(self):
                return BarHandle()

            def __exit__(self, *_args):
                self.exited = True

        bar = BarContext()
        module = types.SimpleNamespace(alive_bar=lambda *_args, **_kwargs: bar)
        with (
            mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True),
            mock.patch.dict(sys.modules, {"alive_progress": module}),
        ):
            progress = Progress(Printer(stream=TtyStringIO()), 2, "Analyzing")
            with progress:
                progress.update("first")
        self.assertEqual(len(updates), 1)
        text, count = updates[0]
        self.assertEqual(count, 1)
        self.assertIn("first", text)
        self.assertIn("\x1b[2m", text)
        self.assertTrue(bar.exited)

    def test_progress_titles_use_a_fixed_display_width_and_ellipsis(self):
        short = _fit_title("image")
        long = _fit_title("牛X啊！Lisa登上《ELLE》杂志金九刊封面及写真美图大赏！")
        self.assertEqual(_cell_width(short), 36)
        self.assertEqual(_cell_width(long), 36)
        self.assertIn("...", long)

    def test_human_final_result_is_grouped_and_quiet_stays_compact(self):
        result = RunResult("Board", 4, 4, 2, 1, 1)
        stream = io.StringIO()
        args = argparse.Namespace(json=False, quiet=0, write=True)
        with mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}):
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
        with mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}):
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
            mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}),
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

    def test_default_tag_output_summarizes_skips_while_verbose_lists_them(self):
        skipped_item = EagleItem("1", "already-tagged", "jpg", [], [], "saved")
        pending_item = item(2)
        scope = BoardScope(
            Board("board", "Board", "Board"), [], [skipped_item, pending_item]
        )
        probe = TagItemResult(
            index=2, item=pending_item, tags=["two"], annotation="two"
        )

        def run(*options: str) -> str:
            stderr = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}),
                mock.patch("moodtag.make_vision_client", return_value=object()),
                mock.patch("moodtag.cli.EagleClient", return_value=Eagle()),
                mock.patch("moodtag.cli.load_board_scope", return_value=scope),
                mock.patch(
                    "moodtag.cli.has_moodboard_notes",
                    side_effect=lambda annotation: annotation == "saved",
                ),
                mock.patch("moodtag.cli.load_profile_taxonomy", return_value={}),
                mock.patch("moodtag.cli.eagle_library_images_root", return_value=None),
                mock.patch("moodtag.cli.analyze_tag_item", return_value=probe),
                mock.patch("moodtag.cli.run_tag_analysis", return_value=iter(())),
                redirect_stderr(stderr),
            ):
                self.assertEqual(
                    moodtag.cli._command_tag_v2(self.tag_args(*options)), 0
                )
            return stderr.getvalue()

        default_output = run()
        self.assertNotIn("Skip already-tagged", default_output)
        self.assertIn("1 skipped", default_output)
        self.assertIn("already-tagged", run("-v"))

    def test_guided_confirmation_clears_the_complete_region_before_tagging(self):
        spinners: list[str] = []

        @contextmanager
        def no_spinner(_printer, text):
            spinners.append(text)
            yield

        scope = BoardScope(Board("board", "Board", "Board"), [], [item(1)])
        args = moodtag.build_parser().parse_args(
            ["tag", "--board", "board", "--mock-model", "--guided-main-flow"]
        )
        with (
            mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}),
            mock.patch("moodtag.cli.spinner", no_spinner),
            mock.patch("moodtag.cli.EagleClient", return_value=Eagle()),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            mock.patch("builtins.input", return_value=""),
            mock.patch("moodtag.cli._command_tag_v2", return_value=0) as command_tag,
        ):
            self.assertEqual(moodtag.cli._command_guided_tag_v2(args), 0)
        command_tag.assert_called_once_with(args)
        self.assertEqual(spinners, ["Scanning Eagle folder…"])

    def test_menu_retries_then_returns_back_and_session_is_exclusive(self):
        stream = io.StringIO()
        printer = Printer(stream=stream, plain=True)
        with (
            mock.patch.dict(os.environ, {"MOODTAG_LANG": "en"}),
            mock.patch("builtins.input", side_effect=["bad", "b"]),
        ):
            self.assertIsNone(choose(printer, "Choose", ["one"], allow_back=True))
        self.assertIn("Enter a valid option.", stream.getvalue())

    def test_key_menu_preserves_terminal_output_postprocessing(self):
        from moodtag.ui import menu

        stream = TtyStringIO()
        original_attrs = [
            termios.OPOST,
            0,
            0,
            termios.ICANON | termios.ECHO,
            0,
            0,
            [0] * 32,
        ]
        original_attrs[6][termios.VMIN] = 1
        calls = []

        def set_attrs(_fd, _when, attrs):
            calls.append(attrs)

        fake_stdin = mock.Mock()
        fake_stdin.fileno.return_value = 9
        with (
            mock.patch("moodtag.ui.menu.sys.stdin", fake_stdin),
            mock.patch(
                "moodtag.ui.menu.termios.tcgetattr", return_value=original_attrs
            ),
            mock.patch("moodtag.ui.menu.termios.tcsetattr", side_effect=set_attrs),
            mock.patch("moodtag.ui.menu.os.read", return_value=b"\n"),
        ):
            self.assertEqual(
                menu._choose_keys(
                    Printer(stream=stream),
                    "Choose",
                    [MenuChoice("one")],
                    allow_back=False,
                    default=None,
                ),
                0,
            )
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0][1] & termios.OPOST)
        self.assertFalse(calls[0][3] & termios.ICANON)
        self.assertFalse(calls[0][3] & termios.ECHO)


if __name__ == "__main__":
    unittest.main()
