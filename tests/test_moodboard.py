import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from moodboard import cli as moodboard
from moodboard_core import layout as layout_core


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
        self.assertIn("moodboard layout plan", by_name["body-design.md"]["content"])
        self.assertIn("moodboard layout inspect", by_name["body-design.md"]["content"])
        self.assertIn("not the layout unit", by_name["body-design.md"]["content"])
        self.assertIn("Design Dimensions", by_name["body-design.md"]["content"])
        self.assertIn(
            "Optional Strategies, Not Templates", by_name["body-design.md"]["content"]
        )
        self.assertIn("Anti-template Review", by_name["body-design.md"]["content"])
        self.assertIn(
            "final reference audit layer", by_name["body-design.md"]["content"]
        )
        self.assertNotIn("Component Grammar", by_name["body-design.md"]["content"])

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
            created_html = Path(created["index_html"]).read_text(encoding="utf-8")
            self.assertIn("<title>Merge-Probe-A</title>", created_html)
            self.assertIn("provides reset/base/utility primitives only", created_html)
            self.assertIn(".visually-hidden", created_html)
            self.assertIn(".container-query", created_html)
            self.assertIn(".media-contain", created_html)

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

    def test_output_write_summary_omits_large_details_but_keeps_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_image = root / "reference.jpg"
            source_image.write_bytes(b"reference")
            code, output = run_cli(
                "project", "create", "--name", "Summary Probe", "--base", str(root)
            )
            self.assertEqual(code, 0, output)
            project_dir = Path(json_stdout(output)["project_dir"])
            body = f'<main class="moodboard-page" id="top"><a href="#top">Top</a><img src="{source_image}" alt="Reference"></main>'

            code, output = run_cli(
                "output",
                "write",
                "--project-dir",
                str(project_dir),
                "--summary",
                input_text=body,
            )
            self.assertEqual(code, 0, output)
            payload = json_stdout(output)
            self.assertTrue(payload["ok"])
            self.assertNotIn("body", payload)
            self.assertEqual(payload["image_processing"]["rewrite_count"], 1)
            self.assertEqual(payload["image_processing"]["missing_count"], 0)
            self.assertTrue(payload["check"]["ok"])
            self.assertEqual(payload["check"]["missing_alt"], [])

            bad_body = '<main class="moodboard-page"><img src="missing.jpg"></main>'
            code, output = run_cli(
                "output",
                "write",
                "--project-dir",
                str(project_dir),
                "--summary",
                input_text=bad_body,
            )
            self.assertEqual(code, 1)
            failed = json_stdout(output)
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["error"], "check_failed")
            self.assertFalse(failed["check"]["ok"])
            self.assertTrue(failed["check"]["missing_alt"])
            self.assertTrue(failed["check"]["missing_local_assets"])

    def test_output_write_accepts_different_body_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = []
            for name in ("anchor.jpg", "detail.jpg", "archive.jpg"):
                path = root / name
                path.write_bytes(name.encode("utf-8"))
                images.append(path)

            bodies = [
                f"""
<style data-moodboard-theme>
  .narrative-field {{ display: grid; gap: 1rem; }}
  .narrative-field img {{ max-inline-size: 100%; block-size: auto; }}
</style>
<main class="narrative-field" id="top">
  <section aria-labelledby="opening">
    <h1 id="opening">Opening Signal</h1>
    <figure>
      <img src="{images[0]}" alt="Anchor reference" width="1200" height="800">
      <figcaption>One image carries the first impression.</figcaption>
    </figure>
  </section>
  <section aria-labelledby="audit">
    <h2 id="audit">Reference audit</h2>
    <img src="{images[2]}" alt="Archive reference" width="900" height="900">
  </section>
</main>
""",
                f"""
<main class="evidence-ledger" id="ledger">
  <h1>Evidence Ledger</h1>
  <table>
    <caption>Reference transfer notes</caption>
    <thead><tr><th scope="col">Role</th><th scope="col">Use</th></tr></thead>
    <tbody><tr><td>Gesture</td><td>Keep the hand detail quiet.</td></tr></tbody>
  </table>
  <aside aria-label="Visual evidence">
    <figure>
      <img src="{images[1]}" alt="Detail reference" width="800" height="1200">
      <figcaption>Detail evidence can sit outside a grid.</figcaption>
    </figure>
  </aside>
  <section aria-labelledby="audit-ledger">
    <h2 id="audit-ledger">Reference audit</h2>
    <figure>
      <img src="{images[2]}" alt="Archive reference" width="900" height="900">
      <figcaption>Audit layer remains possible without a fixed wall component.</figcaption>
    </figure>
  </section>
</main>
""",
            ]

            for index, body in enumerate(bodies, start=1):
                code, output = run_cli(
                    "project",
                    "create",
                    "--name",
                    f"Structure Probe {index}",
                    "--base",
                    str(root),
                )
                self.assertEqual(code, 0, output)
                project_dir = Path(json_stdout(output)["project_dir"])

                code, output = run_cli(
                    "output",
                    "write",
                    "--project-dir",
                    str(project_dir),
                    input_text=body,
                )
                self.assertEqual(code, 0, output)
                payload = json_stdout(output)
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["check"]["ok"])
                self.assertGreaterEqual(len(payload["image_processing"]["rewrites"]), 1)

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

    def test_layout_plan_handles_arbitrary_module_subsets(self):
        items = [
            {"id": "A", "src": "a.jpg", "width": 1600, "height": 1000},
            {"id": "B", "src": "b.jpg", "width": 800, "height": 1200},
            {"id": "C", "src": "c.jpg", "width": 1000, "height": 1000},
            {"id": "D", "src": "d.jpg", "width": 1800, "height": 1000},
            {"id": "E", "src": "e.jpg", "width": 900, "height": 1200},
        ]
        for count in (1, 2, 3, 5):
            plan = layout_core.plan_justified(
                [
                    layout_core.item_from_dict(item, index)
                    for index, item in enumerate(items[:count])
                ],
                container_width=900,
                target_row_height=220,
                gap=10,
            )
            self.assertEqual(plan["kind"], "geometry-plan")
            self.assertFalse(plan["html_output"])
            self.assertEqual(plan["metrics"]["item_count"], count)
            self.assertEqual(len(plan["boxes"]), count)
            self.assertFalse(plan["metrics"]["horizontal_overflow"])
            for row in plan["rows"]:
                if row["justified"]:
                    self.assertAlmostEqual(row["width"], 900, delta=0.6)

    def test_layout_cli_inspect_and_plan_subset_specs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "catalog.json"
            specs_path = Path(tmp) / "specs.json"
            plan_path = Path(tmp) / "plan.json"
            catalog.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "A",
                                "src": "a.jpg",
                                "width": 1200,
                                "height": 800,
                                "caption": "wide",
                            },
                            {
                                "id": "B",
                                "src": "b.jpg",
                                "width": 800,
                                "height": 1200,
                                "caption": "tall",
                            },
                            {
                                "id": "C",
                                "src": "c.jpg",
                                "width": 1000,
                                "height": 1000,
                                "caption": "square",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            code, output = run_cli(
                "layout",
                "inspect",
                "--input",
                str(catalog),
                "--ids",
                "C,A",
                "--output",
                str(specs_path),
            )
            self.assertEqual(code, 0, output)
            specs = json.loads(specs_path.read_text(encoding="utf-8"))
            self.assertEqual(specs["kind"], "image-specs")
            self.assertFalse(specs["html_output"])
            self.assertEqual([item["id"] for item in specs["items"]], ["C", "A"])
            self.assertEqual(specs["items"][0]["width_attr"], 1000)
            self.assertEqual(specs["items"][0]["css_aspect_ratio"], "1000 / 1000")

            code, output = run_cli(
                "layout",
                "plan",
                "--input",
                str(catalog),
                "--ids",
                "C,A",
                "--mode",
                "justified",
                "--container-width",
                "720",
                "--target-row-height",
                "220",
                "--output",
                str(plan_path),
            )
            self.assertEqual(code, 0, output)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["kind"], "geometry-plan")
            self.assertFalse(plan["html_output"])
            self.assertEqual(plan["mode"], "justified")
            self.assertEqual([box["id"] for box in plan["boxes"]], ["C", "A"])

    def test_layout_cli_explicit_modes_return_geometry_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "items": [
                            {"id": "A", "src": "a.jpg", "width": 1200, "height": 800},
                            {"id": "B", "src": "b.jpg", "width": 800, "height": 1200},
                            {"id": "C", "src": "c.jpg", "width": 1000, "height": 1000},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            code, output = run_cli(
                "layout",
                "plan",
                "--input",
                str(catalog),
                "--mode",
                "grid",
                "--columns",
                "2",
                "--cell-aspect-ratio",
                "4:3",
                "--container-width",
                "800",
            )
            self.assertEqual(code, 0, output)
            grid = json_stdout(output)
            self.assertEqual(grid["mode"], "grid")
            self.assertEqual(grid["columns"], 2)
            self.assertEqual(grid["boxes"][1]["column"], 1)
            self.assertFalse(grid["html_output"])

            code, output = run_cli(
                "layout",
                "plan",
                "--input",
                str(catalog),
                "--mode",
                "stack",
                "--container-width",
                "600",
            )
            self.assertEqual(code, 0, output)
            stack = json_stdout(output)
            self.assertEqual(stack["mode"], "stack")
            self.assertEqual(stack["metrics"]["row_count"], 3)
            self.assertFalse(stack["metrics"]["horizontal_overflow"])

    def test_layout_preserves_source_path_spacing(self):
        item = layout_core.item_from_dict(
            {
                "id": "A",
                "src": "/tmp/name  with   spaces.jpg",
                "width": 100,
                "height": 100,
            },
            0,
        )
        self.assertEqual(item.src, "/tmp/name  with   spaces.jpg")


if __name__ == "__main__":
    unittest.main()
