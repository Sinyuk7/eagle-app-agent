import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from moodboard import cli as moodboard


def run_cli(*args, input_text=None):
    buffer = io.StringIO()
    old_stdin = None
    if input_text is not None:
        old_stdin = __import__("sys").stdin
        __import__("sys").stdin = io.StringIO(input_text)
    try:
        with redirect_stdout(buffer):
            code = moodboard.main(list(args))
    finally:
        if old_stdin is not None:
            __import__("sys").stdin = old_stdin
    return code, buffer.getvalue()


def json_stdout(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout was not JSON: {text!r}") from exc


class MoodboardCliTests(unittest.TestCase):
    def test_resources_get_returns_body_spec_only(self):
        code, output = run_cli("resources", "get", "body-design.md", "--json")
        self.assertEqual(code, 0, output)
        payload = json_stdout(output)
        self.assertTrue(payload["ok"])
        by_name = {item["name"]: item for item in payload["resources"]}
        self.assertIn(
            "Generate only an HTML body fragment", by_name["body-design.md"]["content"]
        )

        code, output = run_cli("resources", "get", "starter.html", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json_stdout(output)["error"], "unknown_resource")

    def test_project_preflight_and_create_use_bundled_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli(
                "project", "preflight", "--name", "Merge Probe / A", "--base", tmp
            )
            self.assertEqual(code, 0, output)
            preflight = json_stdout(output)
            self.assertTrue(preflight["ok"])
            self.assertEqual(preflight["project_name"], "Merge-Probe-A")
            self.assertEqual(preflight["requested_project_name"], "Merge-Probe-A")
            self.assertFalse(preflight["deduped"])
            self.assertFalse(preflight["project_exists"])

            code, output = run_cli(
                "project", "create", "--name", "Merge Probe / A", "--base", tmp
            )
            self.assertEqual(code, 0, output)
            created = json_stdout(output)
            self.assertFalse(created["deduped"])
            self.assertTrue(created["created_index"])
            self.assertTrue(Path(created["index_html"]).exists())
            self.assertIn(
                "<title>Merge-Probe-A</title>",
                Path(created["index_html"]).read_text(encoding="utf-8"),
            )

            code, output = run_cli(
                "project", "create", "--name", "Merge Probe / A", "--base", tmp
            )
            self.assertEqual(code, 0, output)
            duplicate = json_stdout(output)
            self.assertTrue(duplicate["deduped"])
            self.assertEqual(duplicate["requested_project_name"], "Merge-Probe-A")
            self.assertEqual(duplicate["project_name"], "Merge-Probe-A_01")
            self.assertTrue(Path(duplicate["index_html"]).exists())

            code, output = run_cli(
                "project",
                "create",
                "--name",
                "Merge Probe / A",
                "--base",
                tmp,
                "--overwrite",
            )
            self.assertEqual(code, 0, output)
            overwritten = json_stdout(output)
            self.assertFalse(overwritten["deduped"])
            self.assertTrue(overwritten["overwritten"])
            self.assertEqual(overwritten["project_name"], "Merge-Probe-A")

    def test_body_apply_preserves_shell_and_materializes_local_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_image = root / "source image.jpg"
            source_image.write_bytes(b"image-bytes")
            code, output = run_cli(
                "project", "create", "--name", "Body Probe", "--base", str(root)
            )
            self.assertEqual(code, 0, output)
            project_dir = Path(json_stdout(output)["project_dir"])
            index_path = project_dir / "index.html"
            original = index_path.read_text(encoding="utf-8")
            body = (
                f'<main class="moodboard-page" id="top">'
                f'<img src="{source_image}" alt="Local">'
                f'<img src="https://example.com/remote.jpg" alt="Remote">'
                f"</main>"
            )

            code, output = run_cli(
                "body",
                "apply",
                "--project-dir",
                str(project_dir),
                "--touch-updated-at",
                input_text=body,
            )
            self.assertEqual(code, 0, output)
            payload = json_stdout(output)
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["image_processing"]["rewrites"]), 1)
            rewritten = payload["image_processing"]["rewrites"][0]["to"]
            self.assertTrue(rewritten.startswith("assets/references/"))
            self.assertTrue((project_dir / rewritten).exists())

            text = index_path.read_text(encoding="utf-8")
            self.assertIn("<head>", original)
            self.assertIn("<head>", text)
            self.assertIn(f'src="{rewritten}"', text)
            self.assertIn('src="https://example.com/remote.jpg"', text)
            self.assertTrue(
                (project_dir / "assets" / "references" / "manifest.json").exists()
            )

    def test_output_write_applies_body_checks_and_reports_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_image = root / "reference.jpg"
            source_image.write_bytes(b"reference")
            code, output = run_cli(
                "project", "create", "--name", "Output Probe", "--base", str(root)
            )
            self.assertEqual(code, 0, output)
            project_dir = Path(json_stdout(output)["project_dir"])
            body = f'<main class="moodboard-page" id="top"><a href="#top">Top</a><img src="{source_image}" alt="Reference"></main>'

            code, output = run_cli(
                "output", "write", "--project-dir", str(project_dir), input_text=body
            )
            self.assertEqual(code, 0, output)
            payload = json_stdout(output)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["check"]["ok"])
            self.assertEqual(len(payload["image_processing"]["rewrites"]), 1)
            self.assertTrue(Path(payload["index_html"]).exists())

            bad_body = '<main class="moodboard-page"><img src="missing.jpg"></main>'
            code, output = run_cli(
                "output",
                "write",
                "--project-dir",
                str(project_dir),
                input_text=bad_body,
            )
            self.assertEqual(code, 1)
            failed = json_stdout(output)
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["error"], "check_failed")
            self.assertFalse(failed["check"]["ok"])

    def test_check_reports_failures_and_e2e_page_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad.html"
            absolute_image = root / "absolute.jpg"
            absolute_image.write_bytes(b"absolute")
            bad.write_text(
                f"""<!doctype html>
<html>
<head><meta name="viewport" content="width=device-width"><title>Bad</title></head>
<body>
<main>
<a href="#missing">Missing target</a>
<img src="missing.jpg">
<img src="{absolute_image}" alt="Absolute asset">
<div id="dup"></div><section id="dup"></section>
</main>
</body>
</html>
""",
                encoding="utf-8",
            )

            code, output = run_cli(
                "check", str(bad), "--check-assets", "--check-links", "--localhost-mode"
            )
            self.assertEqual(code, 1)
            payload = json_stdout(output)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["duplicate_ids"])
            self.assertTrue(payload["missing_alt"])
            self.assertTrue(payload["localhost_unsafe_assets"])

            source_image = root / "reference.jpg"
            source_image.write_bytes(b"reference")
            code, output = run_cli(
                "project", "create", "--name", "E2E Probe", "--base", str(root)
            )
            self.assertEqual(code, 0, output)
            project_dir = Path(json_stdout(output)["project_dir"])
            body = f'<main class="moodboard-page" id="top"><a href="#top">Top</a><img src="{source_image}" alt="Reference"></main>'
            code, output = run_cli(
                "body", "apply", "--project-dir", str(project_dir), input_text=body
            )
            self.assertEqual(code, 0, output)
            code, output = run_cli(
                "check",
                str(project_dir),
                "--check-assets",
                "--check-links",
                "--localhost-mode",
            )
            self.assertEqual(code, 0, output)
            self.assertTrue(json_stdout(output)["ok"])

    def test_serve_preflight_uses_builtin_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            absolute_image = project_dir / "absolute.jpg"
            absolute_image.write_bytes(b"absolute")
            (project_dir / "index.html").write_text(
                f"""<!doctype html>
<html>
<head><meta name="viewport" content="width=device-width"><title>Serve</title></head>
<body>
<main><img src="{absolute_image}" alt="Absolute asset"></main>
</body>
</html>
""",
                encoding="utf-8",
            )

            code, output = run_cli("serve", str(project_dir), "--preflight-localhost")
            self.assertEqual(code, 3, output)
            payload = json_stdout(output)
            self.assertEqual(payload["error"], "localhost_preflight_failed")
            self.assertIn("localhost_unsafe_assets", payload["check"])
            self.assertTrue(payload["check"]["localhost_unsafe_assets"])


if __name__ == "__main__":
    unittest.main()
