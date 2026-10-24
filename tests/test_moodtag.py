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
from moodtag.cli import Board, BoardScope, EagleItem, MoodtagError, SetupCancelled


class MoodtagCliTests(unittest.TestCase):
    def test_config_profile_persists_without_provider_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with (
                mock.patch.dict(
                    os.environ, {"MOODTAG_CONFIG": str(config)}, clear=True
                ),
                mock.patch("moodtag.cli.load_env_defaults"),
            ):
                self.assertEqual(moodtag.main(["config", "profile", "editorial"]), 0)
            saved = config.read_text(encoding="utf-8")
        self.assertIn('"profile": "editorial"', saved)
        self.assertNotIn("protocol", saved)
        self.assertNotIn("api_key", saved)

    def test_tag_without_complete_setup_fails_before_eagle(self):
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch(
                "moodtag.config.config_path",
                return_value=Path("/tmp/moodtag-no-config.json"),
            ),
            mock.patch("moodtag.cli.EagleClient") as eagle,
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main(["tag", "--board", "board"]), 2)
        eagle.assert_not_called()
        self.assertIn("moodtag config model", stderr.getvalue())

    def test_parser_exposes_current_config_workflows(self):
        parser = moodtag.build_parser()
        self.assertEqual(parser.parse_args(["config", "model"]).config_command, "model")
        self.assertEqual(
            parser.parse_args(["config", "profile"]).config_command, "profile"
        )
        self.assertEqual(parser.parse_args(["config", "reset"]).config_command, "reset")

    def test_missing_profile_defaults_to_editorial(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with mock.patch.dict(
                os.environ, {"MOODTAG_CONFIG": str(config)}, clear=True
            ):
                args = moodtag.build_parser().parse_args(["tag", "--board", "board"])
        self.assertEqual(args.profile, "editorial")

    def test_non_tty_no_argument_is_actionable_and_does_not_prompt(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=False),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 2)
        self.assertIn("No board supplied", stderr.getvalue())

    def test_secret_option_is_rejected(self):
        stderr = io.StringIO()
        with mock.patch("moodtag.cli.load_env_defaults"), redirect_stderr(stderr):
            self.assertEqual(
                moodtag.main(["config", "model", "--api-key", "secret"]), 2
            )
        self.assertNotIn("secret", stderr.getvalue())

    def test_tty_no_argument_shows_home_and_quits(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.sys.stdout.isatty", return_value=True),
            mock.patch("builtins.input", return_value="q"),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 0)
        self.assertIn("Moodtag", stderr.getvalue())

    def test_tty_tagging_style_cancel_returns_to_home(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.sys.stdout.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=["2", "q", "q"]),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 0)
        output = stderr.getvalue()
        self.assertIn("Choose tagging style", output)
        self.assertGreaterEqual(output.count("Moodtag"), 2)

    def test_model_setup_cancel_is_not_an_error(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch(
                "moodtag.cli._setup_prompt", side_effect=SetupCancelled("cancelled")
            ),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main(["config", "model"]), 0)
        self.assertIn("Model setup cancelled. Nothing changed.", stderr.getvalue())

    def test_reset_cancel_is_not_an_error(self):
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", return_value="q"),
        ):
            self.assertEqual(moodtag.main(["config", "reset"]), 0)

    def test_model_setup_persists_non_secret_values_and_retains_saved_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            credentials = Path(directory) / ".env"
            config.write_text(
                '{"base_url":"https://old.test/v1","model":"gpt-5.6-terra",'
                '"profile":"default","eagle_api":"http://eagle.test"}\n',
                encoding="utf-8",
            )
            credentials.write_text("MOODTAG_API_KEY=old-secret\n", encoding="utf-8")
            credentials.chmod(0o600)
            stderr = io.StringIO()
            with (
                mock.patch.dict(
                    os.environ, {"MOODTAG_CONFIG": str(config)}, clear=True
                ),
                mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
                mock.patch("moodtag.cli.choose", side_effect=[0, 1, 0]),
                mock.patch("builtins.input", side_effect=["https://new.test/v1"]),
                mock.patch("moodtag.cli.getpass.getpass", return_value=""),
                mock.patch("moodtag.cli.prompt_yes_no", return_value=True),
                redirect_stderr(stderr),
            ):
                self.assertEqual(moodtag.main(["config", "model"]), 0)

            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["base_url"], "https://new.test/v1")
            self.assertEqual(saved["model"], "gpt-5.6-luna")
            self.assertEqual(saved["profile"], "default")
            self.assertEqual(saved["eagle_api"], "http://eagle.test")
            self.assertNotIn("api_key", saved)
            self.assertEqual(
                credentials.read_text(encoding="utf-8"), "MOODTAG_API_KEY=old-secret\n"
            )
            self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("old-secret", stderr.getvalue())

    def test_reset_model_and_everything_clear_expected_values(self):
        for selected, expected in (
            (
                0,
                {
                    "base_url": "https://service.test/v1",
                    "model": "gpt-5.6-luna",
                    "eagle_api": "http://eagle.test",
                },
            ),
            (1, {"profile": "default", "eagle_api": "http://eagle.test"}),
            (2, {"eagle_api": "http://eagle.test"}),
        ):
            with (
                self.subTest(selected=selected),
                tempfile.TemporaryDirectory() as directory,
            ):
                config = Path(directory) / "config.json"
                credentials = Path(directory) / ".env"
                config.write_text(
                    '{"base_url":"https://service.test/v1","model":"gpt-5.6-luna",'
                    '"profile":"default","eagle_api":"http://eagle.test"}\n',
                    encoding="utf-8",
                )
                credentials.write_text(
                    "MOODTAG_API_KEY=old-secret\nOTHER=value\n", encoding="utf-8"
                )
                with (
                    mock.patch.dict(
                        os.environ,
                        {
                            "MOODTAG_CONFIG": str(config),
                            "MOODTAG_API_KEY": "old-secret",
                        },
                        clear=True,
                    ),
                    mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
                    mock.patch("moodtag.cli.choose", return_value=selected),
                    mock.patch("moodtag.cli.prompt_yes_no", return_value=True),
                ):
                    self.assertEqual(moodtag.main(["config", "reset"]), 0)
                    if selected == 0:
                        self.assertEqual(os.environ["MOODTAG_API_KEY"], "old-secret")
                    else:
                        self.assertNotIn("MOODTAG_API_KEY", os.environ)

                saved = json.loads(config.read_text(encoding="utf-8"))
                self.assertEqual(
                    {key: value for key, value in saved.items() if value}, expected
                )
                if selected == 0:
                    self.assertIn(
                        "MOODTAG_API_KEY=old-secret",
                        credentials.read_text(encoding="utf-8"),
                    )
                else:
                    self.assertNotIn(
                        "MOODTAG_API_KEY", credentials.read_text(encoding="utf-8")
                    )
                self.assertIn("OTHER=value", credentials.read_text(encoding="utf-8"))

    def test_guided_tag_selects_ambiguous_board_without_writing(self):
        class AmbiguousEagle:
            def __init__(self):
                self.updates: list[str] = []

            def app_info(self):
                return {}

            def boards(self):
                return [
                    Board("first", "Shared", "Library/First/Shared"),
                    Board("second", "Shared", "Library/Second/Shared"),
                ]

            def list_items(self, board_id):
                return [EagleItem(board_id, f"{board_id}.jpg", "jpg", [], [], "")]

            def update_item(self, item_id, **_kwargs):
                self.updates.append(item_id)

        eagle = AmbiguousEagle()
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", return_value="1"),
            mock.patch("moodtag.cli._command_tag_v2", return_value=0),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main(["Shared", "--mock-model", "--plain"]), 0)

        self.assertIn("Multiple boards match. Choose one:", stderr.getvalue())
        self.assertIn("Library/First/Shared", stderr.getvalue())
        self.assertEqual(eagle.updates, [])

    def test_guided_tag_cancelled_ambiguous_board_never_writes(self):
        boards = [
            Board("first", "Shared", "Library/First/Shared"),
            Board("second", "Shared", "Library/Second/Shared"),
        ]
        eagle = mock.Mock()
        eagle.app_info.return_value = {}
        eagle.boards.return_value = boards
        eagle.list_items.return_value = []
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.EagleClient", return_value=eagle),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.choose", side_effect=moodtag.cli.MenuCancelled),
        ):
            self.assertEqual(moodtag.main(["Shared", "--mock-model", "--plain"]), 0)
        eagle.update_item.assert_not_called()

    def test_ambiguous_board_error_lists_candidates_for_noninteractive_tag(self):
        boards = [
            Board("first", "Shared", "Library/First/Shared"),
            Board("second", "Shared", "Library/Second/Shared"),
        ]
        with self.assertRaisesRegex(MoodtagError, "Board name is ambiguous") as context:
            moodtag.cli.resolve_board("Shared", boards)
        message = str(context.exception)
        self.assertIn("Library/First/Shared (first)", message)
        self.assertIn("Library/Second/Shared (second)", message)

    def test_tty_home_reports_configured_model_without_internal_details(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch(
                "moodtag.cli.load_user_config",
                return_value={
                    "base_url": "https://example.test",
                    "model": "gpt-5.6-luna",
                    "profile": "editorial",
                },
            ),
            mock.patch.dict(os.environ, {"MOODTAG_API_KEY": "test-key"}, clear=True),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.sys.stdout.isatty", return_value=True),
            mock.patch("builtins.input", return_value="q"),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 0)
        output = stderr.getvalue()
        self.assertIn("Model: Ready", output)
        self.assertIn("Tagging style: Editorial", output)
        self.assertIn("Settings", output)
        self.assertIn("1  Tag a board", output)
        self.assertNotIn("gpt-5.6-luna", output)
        self.assertNotIn("example.test", output)

    def test_tty_home_reports_missing_model_configuration(self):
        stderr = io.StringIO()
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.load_user_config", return_value={}),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.sys.stdout.isatty", return_value=True),
            mock.patch("builtins.input", return_value="q"),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 0)
        output = stderr.getvalue()
        self.assertIn("Model: ! Needs setup", output)
        self.assertIn("Tagging style: Editorial", output)

    def test_tty_home_reports_ollama_health_without_api_key(self):
        stderr = io.StringIO()
        config = {
            "source": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen3.5:9b",
            "profile": "editorial",
        }
        fake_client = mock.Mock()
        fake_client.version.return_value = "0.40.8"
        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.load_user_config", return_value=config),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.OllamaVisionClient", return_value=fake_client),
            mock.patch("moodtag.cli.sys.stdin.isatty", return_value=True),
            mock.patch("moodtag.cli.sys.stdout.isatty", return_value=True),
            mock.patch("builtins.input", return_value="q"),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main([]), 0)
        self.assertIn("Ollama ready", stderr.getvalue())
        self.assertIn("Ollama API reachable", stderr.getvalue())

    def test_bare_board_routes_to_guided_tag_and_commands_stay_argparse(self):
        captured = {}

        def command(args):
            captured["board"] = args.board
            captured["guided"] = args.guided_main_flow
            return 0

        with (
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.command_tag", side_effect=command),
        ):
            self.assertEqual(moodtag.main(["MSHGWFME8L6SJ"]), 0)
        self.assertEqual(captured, {"board": "MSHGWFME8L6SJ", "guided": True})
        self.assertEqual(
            moodtag.rewrite_main_argv(["config", "show"]),
            (["config", "show"], False),
        )

    def test_json_result_uses_stdout_only_for_machine_data(self):
        class Eagle:
            def app_info(self):
                return {}

        args = moodtag.build_parser().parse_args(
            ["tag", "--board", "board", "--json", "--plain"]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        scope = BoardScope(Board("id", "name", "board"), [], [])
        with (
            mock.patch("moodtag.make_vision_client", return_value=object()),
            mock.patch("moodtag.EagleClient", return_value=Eagle()),
            mock.patch("moodtag.cli.load_board_scope", return_value=scope),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.cli._command_tag_v2(args), 0)
        result = __import__("json").loads(stdout.getvalue())
        self.assertEqual(result["exit_code"], 0)
        self.assertNotIn("{", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
