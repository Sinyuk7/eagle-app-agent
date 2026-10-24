from __future__ import annotations

import argparse
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from moodtag import cli
from moodtag_core.common import HTTPResponse
from moodtag_core.contract import CoreError
from moodtag_core.envelope import estimate_cost, normalize_usage
from moodtag_core.provider import (
    OllamaVisionClient,
    VisionClient,
    moodtag_json_schema,
    normalize_base_url,
    protocol_url,
    redact,
)
from moodtag_core.response import extract_assistant_content


class SingleProviderProtocolTests(unittest.TestCase):
    def test_ollama_default_preset_explicitly_disables_thinking(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            default_payload = OllamaVisionClient(model="vision").build_payload(
                image, {}
            )
            smoke_payload = OllamaVisionClient(
                model="vision", preset="smoke"
            ).build_payload(image, {})
        self.assertIs(default_payload["think"], False)
        self.assertIs(smoke_payload["think"], False)

    def test_metadata_context_is_per_image_user_content_for_both_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            ollama = OllamaVisionClient(model="vision").build_payload(
                image,
                {},
                original_title="Lookbook",
                source_url="https://example.test/pin?id=private",
            )
            remote = VisionClient(
                protocol="chat",
                base_url="https://example.test/v1",
                model="vision",
                api_key="key",
                profile="default",
            ).build_payload(
                image,
                {},
                original_title="Lookbook",
                source_url="https://example.test/pin?id=private",
            )
        ollama_user = ollama["messages"][1]["content"]
        remote_user = remote["messages"][1]["content"][0]["text"]
        for prompt in (ollama_user, remote_user):
            self.assertIn("Original title: Lookbook", prompt)
            self.assertIn("https://example.test/pin", prompt)
            self.assertNotIn("private", prompt)

    def test_suggest_title_is_required_by_both_profile_schemas(self):
        for profile in ("default", "editorial"):
            schema = moodtag_json_schema(profile)
            self.assertIn("suggest_title", schema["required"])
            self.assertEqual(schema["properties"]["suggest_title"]["type"], "string")
            self.assertTrue(schema["properties"]["suggest_title"]["description"])
            self.assertTrue(schema["properties"]["elements"]["description"])

    def test_image_destination_labels_local_api_and_remote_service(self):
        local = cli.image_destination_message(
            {"protocol": "ollama", "base_url": "http://127.0.0.1:11434"}
        )
        remote = cli.image_destination_message(
            {"protocol": "chat", "base_url": "https://api.example.test/v1"}
        )
        self.assertIn(
            "server-side inference locality cannot be independently verified", local
        )
        self.assertIn("api.example.test", remote)

    @staticmethod
    def analysis_payload() -> dict[str, object]:
        return {
            "brief": "brief",
            "elements": ["subject"],
            "use": "use",
            "key": "key",
            "camera": "camera",
            "light_color": "light",
            "visible_text": [],
            "brand_evidence": [],
            "product_categories": [],
            "commercial_format_confidence": "not_assessed",
            "suggest_title": "",
            "tags": [],
            "use_intents": [],
        }

    def test_protocol_urls_normalize_root_v1_and_full_paths(self):
        self.assertEqual(
            protocol_url("https://example.test", "chat"),
            "https://example.test/v1/chat/completions",
        )
        self.assertEqual(
            protocol_url("https://example.test/v1", "responses"),
            "https://example.test/v1/responses",
        )
        self.assertEqual(
            protocol_url("https://example.test/v1/responses", "responses"),
            "https://example.test/v1/responses",
        )
        with self.assertRaises(CoreError):
            normalize_base_url("example.test/v1", "chat")
        with self.assertRaises(CoreError):
            normalize_base_url("https://example.test/v1?token=secret", "chat")
        with self.assertRaises(CoreError):
            normalize_base_url("https://example.test/v1/responses", "chat")

    def test_chat_payload_uses_chat_wire_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="chat",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            payload = client.build_payload(image, {"style": ["portrait"]})
        self.assertEqual(payload["store"], False)
        self.assertIn("messages", payload)
        self.assertIn("response_format", payload)
        self.assertNotIn("input", payload)
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "text")

    def test_responses_payload_uses_responses_wire_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="responses",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            payload = client.build_payload(image, {"style": ["portrait"]})
        self.assertEqual(payload["store"], False)
        self.assertIn("input", payload)
        self.assertIn("text", payload)
        self.assertNotIn("messages", payload)
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["input"][1]["content"][1]["type"], "input_image")

    def test_gpt_sol_payload_uses_strict_schema_and_prompt_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="responses",
                base_url="https://api.openai.com/v1",
                model="gpt-6.1-sol",
                api_key="custom-secret",
            )
            payload = client.build_payload(image, {"style": ["portrait"]})
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        self.assertNotIn("max_output_tokens", payload)
        self.assertEqual(
            payload["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"}
        )
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(payload["input"][1]["content"][1]["detail"], "auto")

    def test_prompt_cache_prefix_excludes_per_image_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            payload = VisionClient(
                protocol="responses",
                base_url="https://api.openai.com/v1",
                model="gpt-6.1-sol",
                api_key="custom-secret",
            ).build_payload(
                image,
                {"style": ["portrait"]},
                original_title="Per image title",
                source_url="https://example.test/source?secret=value",
            )
        stable = payload["input"][0]["content"][0]["text"]
        dynamic = payload["input"][1]["content"][0]["text"]
        self.assertNotIn("Per image title", stable)
        self.assertNotIn("example.test/source", stable)
        self.assertIn("Per image title", dynamic)
        self.assertIn("https://example.test/source", dynamic)
        self.assertNotIn("secret", dynamic)

    def test_custom_endpoint_does_not_assume_prompt_cache_support(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="responses",
                base_url="https://sub2.de5.net/v1",
                model="gpt-6.1-sol",
                api_key="custom-secret",
            )
            payload = client.build_payload(image, {})
        self.assertNotIn("prompt_cache_options", payload)
        self.assertEqual(payload["input"][0]["role"], "system")

    def test_response_extractors_keep_order_and_reject_empty(self):
        chat = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "a"},
                            {"type": "text", "text": "b"},
                        ]
                    }
                }
            ]
        }
        self.assertEqual(extract_assistant_content(chat), "a\nb")
        responses = {
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "summary_text", "text": "ignore"}],
                },
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "a"},
                        {"type": "output_text", "text": "b"},
                    ],
                },
            ]
        }
        self.assertEqual(extract_assistant_content(responses), "a\nb")
        with self.assertRaisesRegex(CoreError, "refused"):
            extract_assistant_content(
                {"output": [{"content": [{"type": "refusal", "refusal": "no"}]}]}
            )
        with self.assertRaises(CoreError):
            extract_assistant_content({"output": []})

    def test_http_fixtures_cover_chat_and_responses_paths(self):
        requests: list[tuple[str, dict[str, object]]] = []
        payload = self.analysis_payload()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                requests.append((self.path, body))
                if self.path.endswith("/chat/completions"):
                    response = {
                        "choices": [{"message": {"content": json.dumps(payload)}}]
                    }
                else:
                    response = {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": json.dumps(payload)}
                                ],
                            }
                        ],
                    }
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                image = Path(directory) / "image.jpg"
                image.write_bytes(b"jpeg")
                for protocol in ("chat", "responses"):
                    client = VisionClient(
                        protocol=protocol,
                        base_url=f"http://127.0.0.1:{server.server_port}/v1",
                        model="vision",
                        api_key="custom-secret",
                    )
                    client.analyze(image, {}, retries=0, max_tags=3)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(
            [path for path, _body in requests],
            ["/v1/chat/completions", "/v1/responses"],
        )
        self.assertIn("messages", requests[0][1])
        self.assertIn("input", requests[1][1])

    def test_remote_envelope_preserves_response_metadata(self):
        payload = self.analysis_payload()
        response = {
            "id": "resp_test",
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(payload)}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="responses",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            with mock.patch(
                "moodtag_core.remote.http_request_with_metadata",
                return_value=HTTPResponse(
                    response,
                    200,
                    {
                        "X-Request-ID": "req_test",
                        "Retry-After": "2",
                        "Authorization": "Bearer secret",
                    },
                ),
            ):
                envelope = client.analyze_envelope(image, {}, retries=0, max_tags=3)
        self.assertEqual(envelope.data.brief, "brief")
        self.assertEqual(envelope.metadata.response_id, "resp_test")
        self.assertEqual(envelope.metadata.status, "completed")
        self.assertEqual(envelope.metadata.http_status, 200)
        self.assertEqual(envelope.metadata.usage["input_tokens"], 10)
        self.assertEqual(
            envelope.metadata.headers, {"x-request-id": "req_test", "retry-after": "2"}
        )
        self.assertEqual(client.last_attempts[-1].submission_state, "response_received")

    def test_remote_rejects_editorial_response_missing_schema_fields(self):
        payload = self.analysis_payload()
        payload.pop("visible_text")
        response = {"choices": [{"message": {"content": json.dumps(payload)}}]}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="chat",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            with (
                mock.patch(
                    "moodtag_core.remote.http_request_with_metadata",
                    return_value=HTTPResponse(response, 200, {}),
                ),
                self.assertRaisesRegex(CoreError, "missing required fields"),
            ):
                client.analyze(image, {}, retries=0, max_tags=3)

    def test_incomplete_responses_are_rejected_before_business_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="responses",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            with (
                mock.patch(
                    "moodtag_core.remote.http_request_with_metadata",
                    return_value=HTTPResponse(
                        {
                            "status": "incomplete",
                            "incomplete_details": {"reason": "length"},
                        },
                        200,
                        {},
                    ),
                ),
                self.assertRaisesRegex(CoreError, "did not complete"),
            ):
                client.analyze(image, {}, retries=0, max_tags=3)
        self.assertEqual(client.last_attempts[-1].submission_state, "response_received")

    def test_chat_non_success_finish_reason_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.jpg"
            image.write_bytes(b"jpeg")
            client = VisionClient(
                protocol="chat",
                base_url="https://example.test/v1",
                model="vision",
                api_key="custom-secret",
            )
            with (
                mock.patch(
                    "moodtag_core.remote.http_request_with_metadata",
                    return_value=HTTPResponse(
                        {
                            "choices": [
                                {
                                    "finish_reason": "length",
                                    "message": {"content": "{}"},
                                }
                            ]
                        },
                        200,
                        {},
                    ),
                ),
                self.assertRaisesRegex(CoreError, "finish_reason=length"),
            ):
                client.analyze(image, {}, retries=0, max_tags=3)

    def test_ollama_native_payload_and_local_response(self):
        requests: list[tuple[str, dict[str, object]]] = []
        result = self.analysis_payload() | {
            "visible_text": [],
            "brand_evidence": [],
            "product_categories": [],
            "commercial_format_confidence": "not_assessed",
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = {
                    "models": [
                        {
                            "name": "vision:latest",
                            "digest": "sha256:x",
                            "capabilities": ["vision"],
                            "details": {"runner": "mlx"},
                        }
                    ]
                }
                self._send(body)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                requests.append((self.path, body))
                if self.path == "/api/show":
                    self._send(
                        {
                            "capabilities": ["vision"],
                            "details": {"runner": "mlx"},
                            "model_info": {
                                "general.architecture": "qwen3_5",
                                "qwen3_5.context_length": 262144,
                            },
                        }
                    )
                else:
                    self._send(
                        {
                            "done": True,
                            "done_reason": "stop",
                            "message": {"content": json.dumps(result)},
                            "load_duration": 10,
                            "prompt_eval_count": 20,
                        }
                    )

            def _send(self, value):
                encoded = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                image = Path(directory) / "image.jpg"
                image.write_bytes(b"jpeg")
                client = OllamaVisionClient(
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    model="vision:latest",
                    preset="smoke",
                )
                parsed = client.analyze(image, {}, retries=0, max_tags=3)
                self.assertEqual(parsed.brief, "brief")
                self.assertEqual(client.runtime["prompt_eval_count"], 20)
                self.assertEqual(client.runtime["runner"], "mlx")
                self.assertEqual(client.runtime["model_context_capacity"], 262144)
                self.assertGreaterEqual(client.runtime["queue_wait_ms_estimated"], 0)
        finally:
            server.shutdown()
            server.server_close()
        chat = next(body for path, body in requests if path == "/api/chat")
        self.assertEqual(chat["stream"], False)
        self.assertEqual(chat["format"], moodtag_json_schema("editorial"))
        self.assertEqual(chat["options"], {"temperature": 0})
        self.assertNotIn("data:", chat["messages"][1]["images"][0])

    def test_ollama_refuses_remote_signal_without_fallback(self):
        client = OllamaVisionClient(model="vision")
        with self.assertRaisesRegex(CoreError, "local-only"):
            client._check_locality({"model_info": {"remote_host": "host"}})
        with self.assertRaisesRegex(CoreError, "http endpoint"):
            OllamaVisionClient(base_url="https://example.test", model="vision")

    def test_ollama_discovery_uses_show_when_tags_omit_capabilities(self):
        class Probe:
            def models(self):
                return [
                    {"name": "vision-by-metadata"},
                    {"name": "name-is-not-proof:vision"},
                ]

            def inspect_model(self, model):
                return {
                    "capabilities": ["vision"]
                    if model == "vision-by-metadata"
                    else ["completion"]
                }

        self.assertEqual(
            cli.discover_ollama_vision_models(Probe()), ["vision-by-metadata"]
        )

    def test_ollama_schema_rejects_missing_and_extra_fields(self):
        from moodtag_core.provider import validate_json_schema

        schema = moodtag_json_schema("default")
        with self.assertRaisesRegex(CoreError, "missing required fields"):
            validate_json_schema({"brief": "x"}, schema)
        value = {
            key: (
                "x"
                if spec["type"] == "string"
                else ["x"]
                if spec["type"] == "array"
                else None
            )
            for key, spec in schema["properties"].items()
        }
        value.update(
            {
                "use": "x",
                "key": "x",
                "camera": "x",
                "light_color": "x",
                "suggest_title": "",
                "tags": [],
                "use_intents": [],
            }
        )
        value["unexpected"] = "x"
        with self.assertRaisesRegex(CoreError, "unexpected fields"):
            validate_json_schema(value, schema)

    def test_ollama_reads_runner_context_and_estimates_queue_time(self):
        with mock.patch.object(
            cli,
            "make_vision_client",
            side_effect=AssertionError("must not preflight here"),
        ):
            cli.ensure_model_setup(argparse.Namespace(source="ollama", model="vision"))

    def test_retry_reuses_one_endpoint(self):
        requests: list[str] = []
        payload = self.analysis_payload()

        class Handler(BaseHTTPRequestHandler):
            calls = 0

            def do_POST(self):  # noqa: N802
                Handler.calls += 1
                requests.append(self.path)
                if Handler.calls == 1:
                    self.send_response(429)
                    self.send_header("Retry-After", "2")
                    self.end_headers()
                    return
                encoded = json.dumps(
                    {"choices": [{"message": {"content": json.dumps(payload)}}]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                tempfile.TemporaryDirectory() as directory,
                mock.patch("moodtag_core.remote.time.sleep") as sleep,
            ):
                image = Path(directory) / "image.jpg"
                image.write_bytes(b"jpeg")
                client = VisionClient(
                    protocol="chat",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="vision",
                    api_key="custom-secret",
                )
                client.analyze(image, {}, retries=1, max_tags=3)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(requests, ["/v1/chat/completions", "/v1/chat/completions"])
        sleep.assert_called_once_with(2.0)

    def test_redaction_scrubs_arbitrary_secret(self):
        self.assertNotIn(
            "custom-secret", redact("provider said custom-secret", "custom-secret")
        )

    def test_usage_normalization_and_cost_require_known_prices(self):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 6},
            "output_tokens_details": {"reasoning_tokens": 5},
        }
        self.assertEqual(
            normalize_usage(usage),
            {
                "input_tokens": 100,
                "output_tokens": 20,
                "cached_tokens": 40,
                "cache_write_tokens": 6,
                "reasoning_tokens": 5,
            },
        )
        self.assertIsNone(estimate_cost(usage))
        self.assertAlmostEqual(
            estimate_cost(
                usage,
                input_per_million=1.0,
                output_per_million=2.0,
                cached_per_million=0.1,
            ),
            0.000104,
        )

    def test_model_config_rolls_back_when_credential_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(
                '{"base_url":"https://old/v1","model":"gpt-5.6-luna"}\n',
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    "os.environ", {"MOODTAG_CONFIG": str(config)}, clear=True
                ),
                mock.patch.object(
                    cli, "save_env_values", side_effect=OSError("disk full")
                ),
            ):
                with self.assertRaises(OSError):
                    cli._persist_setup(
                        {
                            "base_url": "https://new/v1",
                            "model": "gpt-5.6-terra",
                            "api_key": "custom-secret",
                        }
                    )
            self.assertIn(
                '"model":"gpt-5.6-luna"',
                config.read_text(encoding="utf-8").replace(" ", ""),
            )


if __name__ == "__main__":
    unittest.main()
