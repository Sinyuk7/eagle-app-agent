from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import moodtag


class MoodtagCliTests(unittest.TestCase):
    def test_config_set_and_show_use_single_endpoint_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            with (
                mock.patch.dict(
                    os.environ,
                    {"MOODTAG_CONFIG": str(config)},
                    clear=True,
                ),
                mock.patch("moodtag.cli.load_env_defaults"),
            ):
                self.assertEqual(
                    moodtag.main(
                        [
                            "config",
                            "set",
                            "--protocol",
                            "responses",
                            "--base-url",
                            "https://example.test/v1",
                            "--model",
                            "vision",
                        ]
                    ),
                    0,
                )
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(moodtag.main(["config", "show", "--json"]), 0)
            self.assertIn('"protocol": "responses"', output.getvalue())
            saved = config.read_text(encoding="utf-8")
            self.assertNotIn("fallback", saved)
            self.assertNotIn("api_key", saved)

    def test_tag_without_complete_setup_fails_before_eagle(self):
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("moodtag.cli.load_env_defaults"),
            mock.patch("moodtag.cli.EagleClient") as eagle,
            redirect_stderr(stderr),
        ):
            self.assertEqual(moodtag.main(["tag", "--board", "board"]), 2)
        eagle.assert_not_called()
        self.assertIn("moodtag config setup", stderr.getvalue())

    def test_setup_and_auth_are_available_from_parser(self):
        parser = moodtag.build_parser()
        self.assertEqual(parser.parse_args(["config", "setup"]).config_command, "setup")
        self.assertEqual(parser.parse_args(["config", "auth"]).config_command, "auth")

    def test_non_model_parser_commands_do_not_need_model_setup(self):
        parser = moodtag.build_parser()
        self.assertEqual(
            parser.parse_args(["status", "--board", "board"]).command, "status"
        )
        self.assertEqual(
            parser.parse_args(["reset", "--board", "board"]).command, "reset"
        )

    def test_secret_option_is_rejected(self):
        stderr = io.StringIO()
        with mock.patch("moodtag.cli.load_env_defaults"), redirect_stderr(stderr):
            self.assertEqual(moodtag.main(["config", "set", "--api-key", "secret"]), 2)
        self.assertNotIn("secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
