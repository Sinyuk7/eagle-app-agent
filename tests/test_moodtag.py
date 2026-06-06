import base64
import json
import io
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import moodtag
from scripts import export_moodboard_context
from moodtag_core.contract import (
    DEFAULT_BASE_URL,
    DEFAULT_FALLBACK_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_NO_RESPONSE_FORMAT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)
from moodtag_core.annotation import build_annotation_block
from moodtag_core.prompts import read_system_prompt, render_user_prompt
from moodtag_core.response import normalize_analysis_json
from moodtag_core.taxonomy import render_taxonomy_for_prompt


PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8"
    "z8BQDwAFgwJ/lK3Q2wAAAABJRU5ErkJggg=="
)


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def write_png(path: Path) -> None:
    path.write_bytes(base64.b64decode(PNG_1X1))


def analysis_payload(brief: str = "测试 brief"):
    return {
        "brief": brief,
        "elements": ["白发少女", "角饰", "黑色战术服", "蓝色弹药带", "户外街道"],
        "use": "主要用于测试自然语言 Use 字段，也可作为请求层 contract 参考。",
        "key": "核心视觉抓手是稳定构图和清晰主体，用于确认字段拆解。",
        "camera": "中景平视构图，standard lens feel，主体居中。",
        "light_color": "soft directional light 为主，neutral tone，整体干净。",
        "tags": ["photo"],
        "use_intents": ["lighting_reference"],
    }


class FakeEagle:
    def __init__(self, items, thumbnail_map):
        self.items = items
        self.thumbnail_map = thumbnail_map
        self.updated = []

    def app_info(self):
        return {"version": "test", "buildVersion": "test"}

    def boards(self):
        return [
            moodtag.Board(id="B1", name="Board", path="Board"),
            moodtag.Board(id="B2", name="Nested", path="Root/Nested"),
        ]

    def list_items(self, folder_id):
        assert folder_id in {"B1", "B2"}
        return list(self.items)

    def thumbnail_path(self, item_id):
        return self.thumbnail_map[item_id]

    def update_item(self, item_id, *, tags, annotation):
        self.updated.append((item_id, list(tags), annotation))


class MoodtagTests(unittest.TestCase):
    def test_chat_completions_url_accepts_root_v1_or_full_endpoint(self):
        self.assertEqual(
            moodtag.chat_completions_url("https://api.n1n.ai/"),
            "https://api.n1n.ai/v1/chat/completions",
        )
        self.assertEqual(
            moodtag.chat_completions_url("https://api.n1n.ai/v1"),
            "https://api.n1n.ai/v1/chat/completions",
        )
        self.assertEqual(
            moodtag.chat_completions_url("https://api.n1n.ai/v1/chat/completions"),
            "https://api.n1n.ai/v1/chat/completions",
        )

    def test_models_url_accepts_root_v1_or_full_endpoint(self):
        self.assertEqual(
            moodtag.models_url("https://api.n1n.ai/"),
            "https://api.n1n.ai/v1/models",
        )
        self.assertEqual(
            moodtag.models_url("https://api.n1n.ai/v1"),
            "https://api.n1n.ai/v1/models",
        )
        self.assertEqual(
            moodtag.models_url("https://api.n1n.ai/v1/models"),
            "https://api.n1n.ai/v1/models",
        )

    def test_resolve_board_by_id_name_and_path(self):
        boards = [
            moodtag.Board(id="A", name="Shoot", path="Moodboard/Shoot"),
            moodtag.Board(id="B", name="Other", path="Root/Other"),
        ]
        self.assertEqual(moodtag.resolve_board("A", boards).id, "A")
        self.assertEqual(moodtag.resolve_board("Other", boards).id, "B")
        self.assertEqual(moodtag.resolve_board("Moodboard/Shoot", boards).id, "A")
        self.assertEqual(moodtag.resolve_board("moodboard/Shoot", boards).id, "A")

    def test_resolve_board_duplicate_name_requires_id(self):
        boards = [
            moodtag.Board(id="A", name="Shoot", path="A/Shoot"),
            moodtag.Board(id="B", name="Shoot", path="B/Shoot"),
        ]
        with self.assertRaisesRegex(moodtag.MoodtagError, "ambiguous"):
            moodtag.resolve_board("Shoot", boards)

    def test_replace_and_remove_notes_block(self):
        existing = (
            "Manual note\n\n"
            "Brief: old\n\nElements: old element。\n\nUse: old\n\nKey: old\n\n"
            "Camera: old\n\nLightColor: old\n\n"
            "Tail"
        )
        block = (
            "Brief: new brief\n\nElements: new element。\n\nUse: new use\n\nKey: new key\n\n"
            "Camera: new camera\n\nLightColor: new light"
        )
        updated = moodtag.replace_notes_block(existing, block)
        self.assertIn("Manual note", updated)
        self.assertIn("Tail", updated)
        self.assertIn("new brief", updated)
        self.assertNotIn("old", updated)
        self.assertNotIn("[Moodboard Notes]", updated)
        self.assertTrue(moodtag.has_moodboard_notes(updated))
        cleaned = moodtag.remove_notes_block(updated)
        self.assertIn("Manual note", cleaned)
        self.assertNotIn("Brief:", cleaned)

    def test_old_moodboard_notes_wrapper_is_not_processed(self):
        annotation = "[Moodboard Notes]\nSummary: old\n[/Moodboard Notes]"
        self.assertFalse(moodtag.has_moodboard_notes(annotation))
        self.assertEqual(moodtag.remove_notes_block(annotation), annotation)

    def test_redact_secret(self):
        fake_key = "s" + "k-" + "testExampleSecretForRedaction123456"
        text = f"bad key {fake_key}"
        self.assertNotIn("testExample", moodtag.redact(text))
        self.assertIn("sk-REDACTED", moodtag.redact(text))

    def test_invalid_tag_args_short_circuit_before_eagle(self):
        stderr = io.StringIO()
        with mock.patch.object(
            moodtag, "EagleClient", side_effect=AssertionError("should not touch Eagle")
        ):
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                code = moodtag.main(
                    ["tag", "--board", "Board", "--mock-vl", "--image-edge", "128"]
                )
        self.assertEqual(code, 2)
        self.assertIn("--image-edge", stderr.getvalue())

    def test_validate_vl_result_rejects_empty_result(self):
        with self.assertRaisesRegex(moodtag.MoodtagError, "brief"):
            moodtag.normalize_vl_result(analysis_payload(brief=""))

    def test_normalize_vl_result_accepts_raw_json_content_string(self):
        analysis = moodtag.normalize_vl_result(
            json.dumps(analysis_payload("raw content"), ensure_ascii=False),
            taxonomy={"medium": ["photo"]},
        )
        self.assertEqual(analysis.brief, "raw content")
        self.assertEqual(analysis.tags, ["photo", "lighting ref"])

    def test_load_env_file_sets_defaults_without_overriding_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "export MOODTAG_MODEL='dotenv-model'",
                        "MOODTAG_API_KEY=dotenv-key",
                        "MOODTAG_BASE_URL=https://example.test/v1 # comment",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"MOODTAG_API_KEY": "shell-key"},
                clear=True,
            ):
                moodtag.load_env_file(env_file)
                self.assertEqual(os.environ["MOODTAG_MODEL"], "dotenv-model")
                self.assertEqual(os.environ["MOODTAG_API_KEY"], "shell-key")
                self.assertEqual(
                    os.environ["MOODTAG_BASE_URL"], "https://example.test/v1"
                )

    def test_parser_uses_environment_defaults(self):
        env = {
            "MOODTAG_EAGLE_API": "http://localhost:9999",
            "MOODTAG_BASE_URL": "https://example.test/v1",
            "MOODTAG_FALLBACK_BASE_URL": "https://fallback.example.test/v1",
            "MOODTAG_MODEL": "vision-model",
            "MOODTAG_TAXONOMY": "custom-taxonomy.json",
            "MOODTAG_IMAGE_EDGE": "512",
            "MOODTAG_MAX_TAGS": "7",
            "MOODTAG_RETRIES": "1",
            "MOODTAG_TEMPERATURE": "0.3",
            "MOODTAG_TOP_P": "0.8",
            "MOODTAG_MAX_TOKENS": "321",
            "MOODTAG_NO_RESPONSE_FORMAT": "true",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            parser = moodtag.build_parser()
            args = parser.parse_args(["tag", "--board", "Board", "--mock-vl"])
        self.assertEqual(args.eagle_api, "http://localhost:9999")
        self.assertEqual(args.base_url, "https://example.test/v1")
        self.assertEqual(args.fallback_base_url, "https://fallback.example.test/v1")
        self.assertEqual(args.model, "vision-model")
        self.assertEqual(args.taxonomy, "custom-taxonomy.json")
        self.assertEqual(args.image_edge, 512)
        self.assertEqual(args.max_tags, 7)
        self.assertEqual(args.retries, 1)
        self.assertEqual(args.temperature, 0.3)
        self.assertEqual(args.top_p, 0.8)
        self.assertEqual(args.max_tokens, 321)
        self.assertTrue(args.no_response_format)

    def test_user_config_provides_defaults_without_storing_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            env = {
                "MOODTAG_CONFIG": str(config_path),
                "MOODTAG_API_KEY": "sk-testSecretShouldNotPersist123456",
            }
            with mock.patch.dict(os.environ, env, clear=True):
                with chdir(root):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        code = moodtag.main(
                            [
                                "config",
                                "set",
                                "--base-url",
                                "https://configured.example/v1",
                                "--fallback-base-url",
                                "https://fallback.example/v1",
                                "--model",
                                "configured-model",
                                "--eagle-api",
                                "http://localhost:49999",
                            ]
                        )
                    self.assertEqual(code, 0)
                    raw = config_path.read_text(encoding="utf-8")
                    self.assertIn("configured.example", raw)
                    self.assertNotIn("sk-testSecret", raw)

                    parser = moodtag.build_parser()
                    args = parser.parse_args(["tag", "--board", "Board", "--mock-vl"])
                    self.assertEqual(args.base_url, "https://configured.example/v1")
                    self.assertEqual(args.fallback_base_url, "https://fallback.example/v1")
                    self.assertEqual(args.model, "configured-model")
                    self.assertEqual(args.eagle_api, "http://localhost:49999")

                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = moodtag.main(["config", "show", "--json"])
                    self.assertEqual(code, 0)
                    shown = json.loads(buffer.getvalue())
                    self.assertEqual(shown["api_key"], "set")
                    self.assertNotIn("sk-testSecret", buffer.getvalue())

    def test_environment_overrides_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://configured.example/v1",
                        "model": "configured-model",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "MOODTAG_CONFIG": str(config_path),
                    "MOODTAG_BASE_URL": "https://env.example/v1",
                    "MOODTAG_MODEL": "env-model",
                },
                clear=True,
            ):
                parser = moodtag.build_parser()
                args = parser.parse_args(["tag", "--board", "Board"])
        self.assertEqual(args.base_url, "https://env.example/v1")
        self.assertEqual(args.model, "env-model")

    def test_legacy_default_taxonomy_env_uses_bundled_resource(self):
        with mock.patch.dict(
            os.environ,
            {"MOODTAG_TAXONOMY": "taxonomy/default.json"},
            clear=True,
        ):
            parser = moodtag.build_parser()
            args = parser.parse_args(["tag", "--board", "Board", "--mock-vl"])
            taxonomy = moodtag.load_taxonomy(args.taxonomy)
        self.assertIn("medium", taxonomy)

    def test_parser_defaults_match_reference_provider_contract(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            parser = moodtag.build_parser()
            args = parser.parse_args(["tag", "--board", "Board"])
        self.assertEqual(args.base_url, DEFAULT_BASE_URL)
        self.assertEqual(args.fallback_base_url, DEFAULT_FALLBACK_BASE_URL)
        self.assertEqual(args.model, DEFAULT_MODEL)
        self.assertEqual(args.image_edge, moodtag.DEFAULT_IMAGE_EDGE)
        self.assertEqual(args.temperature, DEFAULT_TEMPERATURE)
        self.assertEqual(args.top_p, DEFAULT_TOP_P)
        self.assertEqual(args.max_tokens, DEFAULT_MAX_TOKENS)
        self.assertEqual(args.no_response_format, DEFAULT_NO_RESPONSE_FORMAT)

    def test_prompt_templates_render_new_json_contract_and_compact_taxonomy(self):
        taxonomy = {"medium": ["photo", "concept art"], "lighting": ["rim light"]}
        system_prompt = read_system_prompt()
        user_prompt = render_user_prompt(taxonomy)
        self.assertIn("Output MUST be raw JSON only", system_prompt)
        self.assertIn("JSON", system_prompt)
        self.assertIn("JSON", user_prompt)
        self.assertIn(
            '{"brief":"","elements":[],"use":"","key":"","camera":"","light_color":"","tags":[],"use_intents":[]',
            user_prompt,
        )
        self.assertIn("subject-verb-object", user_prompt)
        self.assertIn("visible, relatively static, searchable", user_prompt)
        self.assertIn("Do NOT include action/state, camera/framing", user_prompt)
        self.assertIn("medium: photo | concept art", user_prompt)
        self.assertIn("lighting_reference -> lighting ref", user_prompt)
        self.assertNotIn('{\n  "medium"', user_prompt)

    def test_taxonomy_renderer_is_compact_line_format(self):
        rendered = render_taxonomy_for_prompt(
            {"medium": ["photo", "concept art"], "composition": ["full body"]}
        )
        self.assertEqual(
            rendered,
            "medium: photo | concept art\ncomposition: full body",
        )

    def test_response_contract_reconciles_tags_and_use_intents(self):
        taxonomy = {"medium": ["photo"], "pipeline": ["reference"]}
        analysis = normalize_analysis_json(
            {
                **analysis_payload(),
                "tags": ["photo", "unknown tag"],
                "use_intents": ["lighting_reference", "bad_intent"],
            },
            taxonomy=taxonomy,
            max_tags=10,
        )
        self.assertEqual(analysis.tags, ["photo", "lighting ref"])
        self.assertEqual(analysis.use_intents, ["lighting_reference"])
        self.assertEqual(analysis.rejected_tags, ["unknown tag"])
        self.assertEqual(analysis.rejected_use_intents, ["bad_intent"])

    def test_response_contract_requires_elements_array(self):
        payload = analysis_payload()
        del payload["elements"]
        with self.assertRaisesRegex(moodtag.MoodtagError, "elements"):
            moodtag.normalize_vl_result(payload, taxonomy={"medium": ["photo"]})

        payload = analysis_payload()
        payload["elements"] = "白发少女"
        with self.assertRaisesRegex(moodtag.MoodtagError, "elements must be an array"):
            moodtag.normalize_vl_result(payload, taxonomy={"medium": ["photo"]})

        payload = analysis_payload()
        payload["elements"] = []
        with self.assertRaisesRegex(moodtag.MoodtagError, "elements"):
            moodtag.normalize_vl_result(payload, taxonomy={"medium": ["photo"]})

    def test_response_contract_cleans_dedupes_and_limits_elements(self):
        payload = analysis_payload()
        payload["elements"] = [
            "白发少女",
            "白发少女",
            "",
            "角饰；",
            "黑色战术服。",
            "蓝色弹药带",
            "户外街道",
            "漆皮装备",
            "红色角饰",
            "手套",
            "长靴",
            "护具",
            "额外元素",
        ]
        analysis = normalize_analysis_json(
            payload,
            taxonomy={"medium": ["photo"]},
            max_tags=10,
        )
        self.assertEqual(len(analysis.elements), 10)
        self.assertEqual(analysis.elements[:4], ["白发少女", "角饰", "黑色战术服", "蓝色弹药带"])
        self.assertNotIn("", analysis.elements)

    def test_response_contract_accepts_light_color_alias(self):
        payload = analysis_payload()
        payload["lightColor"] = payload.pop("light_color")
        analysis = normalize_analysis_json(
            payload,
            taxonomy={"medium": ["photo"]},
            max_tags=10,
        )
        self.assertEqual(analysis.light_color, "soft directional light 为主，neutral tone，整体干净。")

    def test_annotation_formatter_uses_natural_language_fields_only(self):
        analysis = normalize_analysis_json(
            analysis_payload(),
            taxonomy={"medium": ["photo"]},
            max_tags=10,
        )
        annotation = build_annotation_block(analysis)
        self.assertTrue(annotation.startswith("Brief: "))
        self.assertIn("\n\nElements: 白发少女；角饰；黑色战术服；蓝色弹药带；户外街道。", annotation)
        self.assertIn("\n\nUse: ", annotation)
        self.assertIn("\n\nKey: ", annotation)
        self.assertIn("\n\nCamera: ", annotation)
        self.assertIn("\n\nLightColor: ", annotation)
        self.assertNotIn("[Moodboard Notes]", annotation)
        self.assertNotIn("Tags:", annotation)
        self.assertNotIn("use_intents", annotation)

    def test_locate_original_from_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / "I1.info"
            info.mkdir()
            thumb = info / "image_thumbnail.png"
            original = info / "image.png"
            (info / "metadata.json").write_text("{}", encoding="utf-8")
            write_png(thumb)
            write_png(original)
            item = moodtag.EagleItem(
                id="I1", name="image", ext="png", tags=[], folders=["B1"], annotation=""
            )
            self.assertEqual(moodtag.locate_original_from_thumbnail(thumb, item), original)

    def test_temporary_preview_deletes_file(self):
        if not shutil.which("sips"):
            try:
                import PIL  # noqa: F401
            except ImportError:
                self.skipTest("Pillow or sips is required")
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "tiny.png"
            write_png(original)
            with moodtag.temporary_preview(original, image_edge=256) as preview:
                preview_path = preview.path
                self.assertTrue(preview_path.exists())
                self.assertNotEqual(original, preview_path)
                self.assertEqual(max(preview.width, preview.height), 256)
            self.assertFalse(preview_path.exists())

    def test_tag_dry_run_does_not_update_eagle(self):
        fake, tmp = make_fake_eagle()
        argv = ["tag", "--board", "Board", "--mock-vl", "--limit", "1"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual(fake.updated, [])

    def test_tag_empty_vl_result_fails_without_write(self):
        class EmptyVision:
            def analyze(self, image, taxonomy, retries, max_tags=15):
                del image, taxonomy, retries, max_tags
                raise moodtag.MoodtagError("VL result missing required field: brief")

        fake, tmp = make_fake_eagle()
        argv = ["tag", "--board", "Board", "--write", "--limit", "1"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with mock.patch.object(moodtag, "make_vision_client", return_value=EmptyVision()):
                    with redirect_stdout(io.StringIO()):
                        code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 1)
        self.assertEqual(fake.updated, [])

    def test_tag_write_overwrites_pending_item_metadata(self):
        fake, tmp = make_fake_eagle(
            pending_tags=["manual old tag"],
            pending_annotation="Manual source note",
        )
        argv = ["tag", "--board", "Board", "--mock-vl", "--write"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual(len(fake.updated), 1)
        item_id, tags, annotation = fake.updated[0]
        self.assertEqual(item_id, "I1")
        self.assertEqual(tags, ["photo", "portrait", "beauty", "lighting ref", "pose ref"])
        self.assertNotIn("manual old tag", tags)
        self.assertIn("Brief:", annotation)
        self.assertIn("Elements:", annotation)
        self.assertIn("Use:", annotation)
        self.assertIn("Key:", annotation)
        self.assertIn("Camera:", annotation)
        self.assertIn("LightColor:", annotation)
        self.assertNotIn("Manual source note", annotation)
        self.assertNotIn("[Moodboard Notes]", annotation)
        self.assertNotIn("Tags:", annotation)
        self.assertNotIn("Suggested:", annotation)

    def test_tag_write_skips_existing_notes_without_force(self):
        fake, tmp = make_fake_eagle(processed_first=True)
        argv = ["tag", "--board", "Board", "--mock-vl", "--write", "--limit", "1"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual([item_id for item_id, _, _ in fake.updated], ["I1"])

    def test_tag_force_overwrites_existing_metadata(self):
        fake, tmp = make_fake_eagle()
        argv = ["tag", "--board", "Board", "--mock-vl", "--write", "--force"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual({item_id for item_id, _, _ in fake.updated}, {"I1", "I2"})
        forced = [update for update in fake.updated if update[0] == "I2"][0]
        _, tags, annotation = forced
        self.assertEqual(tags, ["photo", "portrait", "beauty", "lighting ref", "pose ref"])
        self.assertNotIn("old tag", tags)
        self.assertNotIn("old brief", annotation)
        self.assertIn("Brief: 模拟角色", annotation)

    def test_tag_limit_applies_to_pending_items_for_resume(self):
        fake, tmp = make_fake_eagle(processed_first=True, pending_count=2)
        argv = ["tag", "--board", "Board", "--mock-vl", "--write", "--limit", "1"]
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(argv)
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual([item_id for item_id, _, _ in fake.updated], ["I1"])

    def test_brief_prints_stdout_without_secret_or_base64(self):
        fake, tmp = make_fake_eagle()
        buffer = io.StringIO()
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(buffer):
                    code = moodtag.main(["brief", "--board", "Board"])
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("Moodboard Brief", text)
        self.assertIn("I1", text)
        self.assertNotIn("base64", text.lower())
        self.assertNotIn("sk-", text)

    def test_reset_write_clears_notes_and_tags(self):
        fake, tmp = make_fake_eagle()
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(io.StringIO()):
                    code = moodtag.main(["reset", "--board", "Board", "--write"])
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        self.assertEqual(len(fake.updated), 1)
        _, tags, annotation = fake.updated[0]
        self.assertEqual(tags, [])
        self.assertNotIn("Moodboard Notes", annotation)
        self.assertNotIn("Brief:", annotation)
        self.assertNotIn("Elements:", annotation)

    def test_vision_client_retries_then_succeeds(self):
        attempts = {"count": 0}

        class RetryHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib callback name
                attempts["count"] += 1
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if attempts["count"] == 1:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"temporary"}')
                    return
                content = json.dumps(analysis_payload("retry success"))
                body = json.dumps({"choices": [{"message": {"content": content}}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A002 - stdlib signature
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), RetryHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                image = Path(tmp) / "image.png"
                write_png(image)
                client = moodtag.VisionClient(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    model="vision",
                    api_key="sk-testSecretForRetry123456",
                )
                with mock.patch.object(moodtag.time, "sleep"):
                    result = client.analyze(
                        image, {"medium": ["photo"]}, retries=1
                    )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(result.brief, "retry success")

    def test_vision_client_payload_matches_reference_provider_contract(self):
        requests = []

        class PayloadHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib callback name
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payload = json.loads(body.decode("utf-8"))
                requests.append({"path": self.path, "payload": payload})
                content = json.dumps(analysis_payload("payload success"))
                response = json.dumps({"choices": [{"message": {"content": content}}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A002 - stdlib signature
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), PayloadHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                image = Path(tmp) / "image.png"
                write_png(image)
                client = moodtag.VisionClient(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="qwen3.5-122b-a10b",
                    api_key="sk-testSecretForPayload123456",
                    response_format=False,
                    temperature=0.2,
                    top_p=0.9,
                    max_tokens=512,
                )
                result = client.analyze(image, {"medium": ["photo"]}, retries=0)
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result.brief, "payload success")
        self.assertEqual(requests[0]["path"], "/v1/chat/completions")
        payload = requests[0]["payload"]
        self.assertEqual(payload["model"], "qwen3.5-122b-a10b")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertNotIn("response_format", payload)
        user_content = payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "image_url")
        self.assertTrue(user_content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(user_content[1]["type"], "text")
        self.assertIn('"brief":"","elements":[],"use":"","key":"","camera":"","light_color":"","tags":[],"use_intents":[]', user_content[1]["text"])
        self.assertIn("medium: photo", user_content[1]["text"])
        self.assertNotIn('{\n  "medium"', user_content[1]["text"])

    def test_vision_payload_sends_json_response_format_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image.png"
            write_png(image)
            client = moodtag.VisionClient(
                base_url="https://example.test/v1",
                model="qwen3.5-122b-a10b",
                api_key="sk-testSecretForPayload123456",
            )
            payload = client.build_payload(image, {"medium": ["photo"]})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("JSON", payload["messages"][0]["content"])
        self.assertIn("JSON", payload["messages"][1]["content"][1]["text"])

    def test_export_context_subcommand_prints_markdown(self):
        fake, tmp = make_fake_eagle(processed_first=True)
        buffer = io.StringIO()
        try:
            with mock.patch.object(moodtag, "EagleClient", return_value=fake):
                with redirect_stdout(buffer):
                    code = moodtag.main(["export-context", "--board", "Board"])
        finally:
            tmp.cleanup()
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("# Moodboard Context: Board", text)
        self.assertIn("ID: I2", text)
        self.assertNotIn("ID: I1", text)

    def test_export_context_wrapper_calls_new_subcommand(self):
        with mock.patch("scripts.export_moodboard_context.moodtag_main", return_value=0) as main:
            code = export_moodboard_context.main(["--board", "Board"])
        self.assertEqual(code, 0)
        main.assert_called_once_with(["export-context", "--board", "Board"])

    def test_python_module_help_runs_from_outside_repo(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        proc = subprocess.run(
            [sys.executable, "-m", "moodtag", "--help"],
            cwd="/tmp",
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("export-context", proc.stdout)

    def test_vision_client_uses_fallback_base_url(self):
        requests = []

        class FallbackHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib callback name
                requests.append(self.path)
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                content = json.dumps(analysis_payload("fallback success"))
                body = json.dumps({"choices": [{"message": {"content": content}}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A002 - stdlib signature
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), FallbackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                image = Path(tmp) / "image.png"
                write_png(image)
                client = moodtag.VisionClient(
                    base_url="http://127.0.0.1:1/v1",
                    fallback_base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="vision",
                    api_key="sk-testSecretForFallback123456",
                )
                result = client.analyze(image, {"medium": ["photo"]}, retries=0)
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(requests, ["/v1/chat/completions"])
        self.assertEqual(result.brief, "fallback success")


def make_fake_eagle(
    processed_first=False,
    pending_count=1,
    pending_tags=None,
    pending_annotation="",
):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    i1 = root / "I1.info"
    i2 = root / "I2.info"
    i3 = root / "I3.info"
    i1.mkdir()
    i2.mkdir()
    i3.mkdir()
    write_png(i1 / "pending.png")
    write_png(i1 / "pending_thumbnail.png")
    write_png(i2 / "processed.png")
    write_png(i2 / "processed_thumbnail.png")
    write_png(i3 / "pending-extra.png")
    write_png(i3 / "pending-extra_thumbnail.png")
    pending_items = [
        moodtag.EagleItem(
            id="I1",
            name="pending",
            ext="png",
            tags=list(pending_tags or []),
            folders=["B1"],
            annotation=pending_annotation,
        )
    ]
    if pending_count > 1:
        pending_items.append(
            moodtag.EagleItem(
                id="I3",
                name="pending-extra",
                ext="png",
                tags=[],
                folders=["B1"],
                annotation="",
            )
        )
    processed_item = moodtag.EagleItem(
        id="I2",
        name="processed",
        ext="png",
        tags=["old tag"],
        folders=["B1"],
        annotation=(
            "Manual\n\nBrief: old brief\n\nElements: old element。\n\nUse: old use\n\nKey: old key\n\n"
            "Camera: old camera\n\nLightColor: old light"
        ),
    )
    if processed_first:
        items = [processed_item, *pending_items]
    else:
        items = [*pending_items, processed_item]
    fake = FakeEagle(
        items,
        {
            "I1": i1 / "pending_thumbnail.png",
            "I2": i2 / "processed_thumbnail.png",
            "I3": i3 / "pending-extra_thumbnail.png",
        },
    )
    return fake, tmp


if __name__ == "__main__":
    unittest.main()
