from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from moodtag.config import load_user_config, save_user_config
from moodtag_core.catalog import load_model_catalog, protocol_for_model
from moodtag_core.contract import CoreError


class ModelCatalogTests(unittest.TestCase):
    def test_bundled_catalog_has_required_models_and_protocols(self):
        entries = {entry.id: entry for entry in load_model_catalog()}
        self.assertEqual(entries["qwen3.5-122b-a10b"].protocol, "chat")
        self.assertTrue(entries["gpt-5.6-luna"].recommended)
        self.assertEqual(protocol_for_model("gpt-5.6-terra"), "responses")

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
