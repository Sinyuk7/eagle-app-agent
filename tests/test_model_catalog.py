from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from moodtag import cli
from moodtag.config import (
    ACTIVE_PROFILE_KEY,
    NAMED_PROFILES_KEY,
    load_user_config,
    save_user_config,
)
from moodtag_core.catalog import load_model_catalog, protocol_for_model
from moodtag_core.contract import CoreError


class ModelCatalogTests(unittest.TestCase):
    def test_legacy_endpoint_infers_cloud_source_and_preserves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {"base_url": "https://example.test/v1", "model": "gpt-5.6-luna"}
                ),
                encoding="utf-8",
            )
            config = load_user_config(path)
            self.assertNotIn("source", config)
            saved = save_user_config(config, path)
            self.assertEqual(
                load_user_config(saved)["base_url"], "https://example.test/v1"
            )

    def test_ollama_source_and_preset_survive_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_user_config(
                {
                    "source": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "model": "qwen3.5:9b",
                    "ollama_preset": "qwen-instruct",
                },
                path,
            )
            self.assertEqual(load_user_config(path)["source"], "ollama")
            self.assertEqual(load_user_config(path)["ollama_preset"], "qwen-instruct")

    def test_named_profiles_keep_legacy_endpoint_and_select_active_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "base_url": "https://legacy.test/v1",
                        "model": "gpt-5.6-luna",
                        "active_model_profile": "local-qwen",
                        "model_profiles": {
                            "local-qwen": {
                                "source": "ollama",
                                "base_url": "http://127.0.0.1:11434",
                                "model": "qwen3.5:9b",
                            },
                            "cloud": {
                                "source": "openai-compatible",
                                "base_url": "https://cloud.test/v1",
                                "model": "gpt-5.6-luna",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_user_config(path)
        self.assertEqual(config["source"], "ollama")
        self.assertEqual(config["model"], "qwen3.5:9b")
        profiles = json.loads(config[NAMED_PROFILES_KEY])
        self.assertEqual(set(profiles), {"local-qwen", "cloud"})
        self.assertEqual(config[ACTIVE_PROFILE_KEY], "local-qwen")

    def test_cli_switches_between_named_model_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_user_config(
                {
                    "source": "ollama",
                    "model": "qwen3.5:9b",
                    "base_url": "http://127.0.0.1:11434",
                    NAMED_PROFILES_KEY: json.dumps(
                        {
                            "local": {
                                "source": "ollama",
                                "model": "qwen3.5:9b",
                                "base_url": "http://127.0.0.1:11434",
                            },
                            "cloud": {
                                "source": "openai-compatible",
                                "model": "gpt-5.6-luna",
                                "base_url": "https://api.test/v1",
                            },
                        }
                    ),
                },
                path,
            )
            with mock.patch.dict("os.environ", {"MOODTAG_CONFIG": str(path)}):
                cli.command_config_model(Namespace(profile_id="cloud"))
                config = load_user_config(path)
        self.assertEqual(config[ACTIVE_PROFILE_KEY], "cloud")
        self.assertEqual(config["source"], "openai-compatible")
        self.assertEqual(config["model"], "gpt-5.6-luna")

    def test_bundled_catalog_has_required_models_and_protocols(self):
        entries = {entry.id: entry for entry in load_model_catalog()}
        self.assertEqual(entries["qwen3.5-122b-a10b"].protocol, "chat")
        self.assertTrue(entries["gpt-6.1-sol"].recommended)
        self.assertEqual(protocol_for_model("gpt-6.1-sol"), "responses")

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(CoreError):
            protocol_for_model("not-a-catalog-model")

    def test_clean_config_discards_legacy_protocol_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "protocol": "chat",
                        "base_url": "https://example.test",
                        "model": "gpt-5.6-luna",
                    }
                ),
                encoding="utf-8",
            )
            config = load_user_config(path)
            save_user_config(config, path)
            saved = path.read_text(encoding="utf-8")
        self.assertNotIn("protocol", saved)
        self.assertEqual(config["model"], "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
