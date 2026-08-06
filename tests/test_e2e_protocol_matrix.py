from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "e2e_protocol_matrix.py"
FOLDER_ID = "MSHGWFME8L6SJ"
SECRET_ENVS = (
    "MOODTAG_E2E_RESPONSES_API_KEY",
    "MOODTAG_E2E_CHAT_API_KEY",
)


class ProtocolMatrixSafetyTests(unittest.TestCase):
    @staticmethod
    def clean_env() -> dict[str, str]:
        env = os.environ.copy()
        for name in SECRET_ENVS:
            env.pop(name, None)
        return env

    def run_matrix(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            env=self.clean_env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_plan_exposes_only_public_profile_configuration(self):
        result = self.run_matrix("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["folder_id"], FOLDER_ID)
        self.assertEqual(
            [profile["endpoint_url"] for profile in payload["profiles"]],
            [
                "https://sub2.de5.net/v1/responses",
                "https://sub2.de5.net/v1/responses",
                "https://llm-api.net/v1/chat/completions",
            ],
        )
        self.assertNotIn("MOODTAG_API_KEY", result.stdout)

    def test_reset_requires_exact_folder_confirmation(self):
        result = self.run_matrix()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"--confirm-reset {FOLDER_ID}", result.stderr)

    def test_missing_credentials_fail_before_child_process(self):
        result = self.run_matrix("--confirm-reset", FOLDER_ID)
        self.assertNotEqual(result.returncode, 0)
        for name in SECRET_ENVS:
            self.assertIn(name, result.stderr)


if __name__ == "__main__":
    unittest.main()
