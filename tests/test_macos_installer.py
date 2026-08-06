import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "packaging" / "macos" / "build_installer.sh"
SMOKE_SCRIPT = ROOT / "packaging" / "macos" / "smoke_check.sh"
DMG_README = ROOT / "packaging" / "macos" / "DMG-README.txt"


class MacOSInstallerContractTests(unittest.TestCase):
    def test_build_script_creates_pkg_and_dmg_for_arm64(self):
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--target-architecture arm64", text)
        self.assertIn("packaging/macos/entrypoint.py", text)
        self.assertIn('--paths "$ROOT"', text)
        self.assertIn("pkgbuild", text)
        self.assertIn("hdiutil create", text)
        self.assertIn("/usr/local/libexec/moodtag", text)
        self.assertIn("/usr/local/bin", text)

    def test_smoke_check_validates_path_and_help(self):
        text = SMOKE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("pkgutil --payload-files", text)
        self.assertIn("sed 's#^\\./##'", text)
        self.assertIn("PACKAGE_PARENT", text)
        self.assertIn("command -v moodtag", text)
        self.assertIn("moodtag --help", text)
        self.assertIn("/usr/local/bin/moodtag", text)
        self.assertIn('file -L "$COMMAND_PATH"', text)

    def test_dmg_guidance_matches_main_user_flow(self):
        text = DMG_README.read_text(encoding="utf-8")
        self.assertIn("moodtag <board-url-or-id>", text)
        self.assertIn("Python, uv, npm, and Homebrew", text)
        self.assertIn("~/.config/moodtag/.env", text)
        self.assertIn("Privacy &", text)


if __name__ == "__main__":
    unittest.main()
