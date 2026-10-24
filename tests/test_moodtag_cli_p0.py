from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import moodtag
from moodtag.cli import Board, BoardScope, normalize_board_query


class _Eagle:
    def app_info(self):
        return {}


class MoodtagCliP0Tests(unittest.TestCase):
    def test_app_info_uses_documented_eagle_endpoint(self):
        payload = {"status": "success", "data": {"version": "4.0.0"}}
        with mock.patch("moodtag.cli.http_request", return_value=payload) as request:
            result = moodtag.cli.EagleClient("http://eagle.test/").app_info()

        self.assertEqual(result, {"version": "4.0.0"})
        request.assert_called_once_with(
            "GET", "http://eagle.test/api/application/info", timeout=5
        )

    def test_board_query_accepts_eagle_and_relative_folder_links(self):
        expected = "MC1W4IJLB9VWS"
        self.assertEqual(normalize_board_query(f"eagle://folder/{expected}"), expected)
        self.assertEqual(normalize_board_query(f"/folder/{expected}"), expected)
        self.assertEqual(
            normalize_board_query(f"http://localhost:41595/folder?id={expected}"),
            expected,
        )

    def test_max_board_items_default_is_9999(self):
        parser = moodtag.cli.build_parser()
        args = parser.parse_args(["status", "--board", "BOARD"])

        self.assertEqual(args.max_board_items, 9999)

    def _empty_scope(self) -> BoardScope:
        return BoardScope(Board("id", "Board", "Board"), [], [])

    def test_public_tag_json_keeps_stdout_machine_only(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.EagleClient", return_value=_Eagle()),
            mock.patch(
                "moodtag.cli.load_board_scope", return_value=self._empty_scope()
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = moodtag.main(
                ["tag", "--board", "board", "--mock-model", "--json", "--plain"]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["exit_code"], 0)
        self.assertNotIn("{", stderr.getvalue())
        self.assertNotIn("\x1b[", stdout.getvalue())

    def test_profile_override_is_one_run_only(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"profile":"editorial"}\n', encoding="utf-8")
            with (
                mock.patch.dict(
                    os.environ,
                    {"MOODTAG_CONFIG": str(config)},
                    clear=True,
                ),
                mock.patch("moodtag.cli.load_env_defaults"),
                mock.patch("moodtag.cli.EagleClient", return_value=_Eagle()),
                mock.patch(
                    "moodtag.cli.load_board_scope", return_value=self._empty_scope()
                ),
            ):
                self.assertEqual(
                    moodtag.main(
                        [
                            "tag",
                            "--board",
                            "board",
                            "--mock-model",
                            "--profile",
                            "default",
                            "--plain",
                            "-q",
                        ]
                    ),
                    0,
                )
            saved = json.loads(config.read_text(encoding="utf-8"))

        self.assertEqual(saved["profile"], "editorial")

    def test_unknown_profile_fails_before_eagle(self):
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.EagleClient") as eagle,
            redirect_stderr(stderr),
        ):
            code = moodtag.main(
                ["tag", "--board", "board", "--mock-model", "--profile", "unknown"]
            )

        self.assertEqual(code, 2)
        eagle.assert_not_called()
        self.assertIn("Unknown tagging style", stderr.getvalue())

    def test_config_show_json_is_public_stdout_contract(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with (
                mock.patch.dict(
                    os.environ,
                    {"MOODTAG_CONFIG": str(config)},
                    clear=True,
                ),
                mock.patch("moodtag.cli.load_env_defaults"),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                self.assertEqual(moodtag.main(["config", "show", "--json"]), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["profile"], "editorial")
        self.assertEqual(stderr.getvalue(), "")

    def test_interactive_setup_keeps_human_output_on_stderr(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        values = {
            "base_url": "https://example.test/v1",
            "model": "gpt-5.6-luna",
            "api_key": "test-key",
        }
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with (
                mock.patch.dict(
                    os.environ,
                    {"MOODTAG_CONFIG": str(config)},
                    clear=True,
                ),
                mock.patch("moodtag.cli.load_env_defaults"),
                mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
                mock.patch("moodtag.cli._setup_prompt", return_value=values),
                mock.patch("moodtag.cli.prompt_yes_no", return_value=True),
                mock.patch("moodtag.cli._persist_setup"),
                mock.patch("moodtag.cli.EagleClient", return_value=_Eagle()),
                mock.patch(
                    "moodtag.cli.load_board_scope", return_value=self._empty_scope()
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                self.assertEqual(moodtag.main(["MSHGWFME8L6SJ"]), 0)

        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Nothing to process.", stderr.getvalue())
        self.assertNotIn("test-key", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
