#!/usr/bin/env python3
"""Real Eagle E2E checks for moodtag.

The suite uses a real Eagle desktop Web API and a local OpenAI-compatible
vision stub. This validates CLI wiring, Eagle item import/update/reset, retry
handling, and guard rails without spending external model credits.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import moodtag  # noqa: E402


TEST_FOLDER = "__moodtag_e2e__"
ITEM_PREFIX = "moodtag-e2e-"
E2E_API_KEY = "sk-e2eLocalStubForMoodtagOnly123456"
E2E_MODEL = "e2e-vision"
PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8"
    "z8BQDwAFgwJ/lK3Q2wAAAABJRU5ErkJggg=="
)


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float


@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str
    command: CommandResult | None = None


class E2EFailure(AssertionError):
    pass


class VisionStub:
    def __init__(self, *, failures_before_success: int = 0, empty_result: bool = False):
        self.failures_before_success = failures_before_success
        self.empty_result = empty_result
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not running")
        return f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self) -> "VisionStub":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    payload = {}
                owner.requests.append(
                    {
                        "path": self.path,
                        "model": payload.get("model"),
                        "has_response_format": "response_format" in payload,
                        "has_image": has_image_payload(payload),
                        "user_agent": self.headers.get("User-Agent", ""),
                    }
                )
                if len(owner.requests) <= owner.failures_before_success:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"temporary e2e failure"}')
                    return

                result = {
                    "brief": "白发测试角色站在中性背景前，身穿黑色测试服并佩戴蓝色道具。",
                    "elements": ["白发测试角色", "黑色测试服", "蓝色道具", "中性背景", "角色配饰"],
                    "use": "主要用于 E2E 流程验证，也可作为无 wrapper annotation 测试参考。",
                    "key": "核心是确认模型 JSON 能拆成自然语言备注和 Eagle tags。",
                    "camera": "中景平视构图，standard lens feel，主体居中。",
                    "light_color": "soft test light 为主，neutral tone，整体稳定。",
                    "tags": ["photo", "portrait", "reference"],
                    "use_intents": ["lighting_reference", "pose_reference"],
                }
                if owner.empty_result:
                    result = {
                        "brief": "",
                        "elements": [],
                        "use": "",
                        "key": "",
                        "camera": "",
                        "light_color": "",
                        "tags": [],
                        "use_intents": [],
                    }
                body = {
                    "choices": [
                        {"message": {"role": "assistant", "content": json.dumps(result)}}
                    ]
                }
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def has_image_payload(payload: dict[str, Any]) -> bool:
    for message in payload.get("messages", []):
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


class E2E:
    def __init__(self, *, eagle_api: str, python: str, board_query: str = "") -> None:
        self.eagle_api = eagle_api
        self.python = python
        self.eagle = moodtag.EagleClient(eagle_api)
        self.folder = self.resolve_test_folder(board_query)
        self.created_item_ids: set[str] = set()

    def resolve_test_folder(self, query: str) -> moodtag.Board:
        self.eagle.app_info()
        boards = self.eagle.boards()
        if query:
            return moodtag.resolve_board(query, boards)
        for board in boards:
            if board.path == TEST_FOLDER:
                return board
        if not boards:
            raise E2EFailure("Eagle has no folders available for E2E")
        return boards[0]

    def run(self) -> list[CaseResult]:
        cases = [
            self.case_core_write_brief_reset,
            self.case_core_dry_run,
            self.case_force_overwrite,
            self.case_boundary_short_circuit,
            self.case_failure_retry,
            self.case_severe_empty_result,
        ]
        results: list[CaseResult] = []
        for case in cases:
            self.cleanup_test_items()
            try:
                result = case()
                results.append(result)
            except Exception as exc:  # noqa: BLE001 - keep suite diagnostics
                results.append(CaseResult(case.__name__, False, moodtag.redact(str(exc))))
        self.cleanup_test_items()
        return results

    def case_core_write_brief_reset(self) -> CaseResult:
        item = self.add_test_item("core")
        with VisionStub() as stub:
            tag = self.moodtag(
                [
                    "tag",
                    "--board",
                    self.folder.id,
                    "--write",
                    "--limit",
                    "1",
                    "--image-edge",
                    "256",
                ],
                vision_base_url=stub.base_url,
            )
            assert_ok(tag, "tag --write should succeed")
            assert_equal(len(stub.requests), 1, "vision request count")
            request = stub.requests[0]
            assert_equal(request["path"], "/v1/chat/completions", "vision path")
            assert_true(request["has_image"], "vision payload includes image")
            assert_equal(request["model"], E2E_MODEL, "vision model")

        updated = self.eagle.item_info(item.id)
        assert_true(moodtag.has_moodboard_notes(updated.annotation), "notes written")
        assert_true("[Moodboard Notes]" not in updated.annotation, "wrapper not written")
        assert_true("Tags:" not in updated.annotation, "tags not written in annotation")
        assert_true("Elements:" in updated.annotation, "elements written")
        assert_true("photo" in updated.tags, "photo tag written")
        assert_true("portrait" in updated.tags, "portrait tag written")

        status = self.moodtag(["status", "--board", self.folder.id])
        assert_ok(status, "status should succeed")
        assert_in("Processed: 1", status.stdout, "status processed count")

        brief = self.moodtag(["brief", "--board", self.folder.id])
        assert_ok(brief, "brief should succeed")
        assert_in("白发测试角色", brief.stdout, "brief includes notes brief")

        reset = self.moodtag(["reset", "--board", self.folder.id, "--write"])
        assert_ok(reset, "reset --write should succeed")
        reset_item = self.eagle.item_info(item.id)
        assert_true(
            not moodtag.has_moodboard_notes(reset_item.annotation), "notes reset"
        )
        assert_equal(reset_item.tags, [], "reset clears tags")
        return CaseResult(
            "core_write_brief_reset",
            True,
            "real Eagle import -> tag write -> status -> brief -> reset clears metadata",
            reset,
        )

    def case_core_dry_run(self) -> CaseResult:
        item = self.add_test_item("dry-run")
        with VisionStub() as stub:
            result = self.moodtag(
                [
                    "tag",
                    "--board",
                    self.folder.id,
                    "--limit",
                    "1",
                    "--image-edge",
                    "256",
                ],
                vision_base_url=stub.base_url,
            )
            assert_ok(result, "dry-run tag should succeed")
            assert_equal(len(stub.requests), 1, "vision request count")
        current = self.eagle.item_info(item.id)
        assert_true(
            not moodtag.has_moodboard_notes(current.annotation),
            "dry run does not write notes",
        )
        assert_true("photo" not in current.tags, "dry run does not write tags")
        return CaseResult(
            "core_dry_run",
            True,
            "real Eagle import -> vision analysis -> no write passed",
            result,
        )

    def case_force_overwrite(self) -> CaseResult:
        item = self.add_test_item("force-overwrite")
        self.eagle.update_item(
            item.id,
            tags=["manual old tag"],
            annotation=(
                "Brief: old brief\n\nUse: old use\n\nKey: old key\n\n"
                "Camera: old camera\n\nLightColor: old light"
            ),
        )
        with VisionStub() as stub:
            result = self.moodtag(
                [
                    "tag",
                    "--board",
                    self.folder.id,
                    "--write",
                    "--force",
                    "--limit",
                    "1",
                    "--image-edge",
                    "256",
                ],
                vision_base_url=stub.base_url,
            )
            assert_ok(result, "force tag should succeed")
            assert_equal(len(stub.requests), 1, "force request count")
        updated = self.eagle.item_info(item.id)
        assert_true(moodtag.has_moodboard_notes(updated.annotation), "force wrote notes")
        assert_true("old brief" not in updated.annotation, "old annotation overwritten")
        assert_true("Elements:" in updated.annotation, "new elements written")
        assert_true("manual old tag" not in updated.tags, "old tags overwritten")
        assert_equal(
            updated.tags,
            ["photo", "portrait", "reference", "lighting ref", "pose ref"],
            "force writes only model tags",
        )
        return CaseResult(
            "force_overwrite",
            True,
            "force write overwrites existing annotation and tags",
            result,
        )

    def case_boundary_short_circuit(self) -> CaseResult:
        before = self.folder_item_count()
        result = self.moodtag(
            [
                "tag",
                "--board",
                self.folder.id,
                "--eagle-api",
                "http://127.0.0.1:9",
                "--mock-vl",
                "--image-edge",
                "128",
            ]
        )
        assert_equal(result.returncode, 2, "invalid image-edge exit")
        assert_in("--image-edge", result.stderr, "short-circuit error")
        assert_equal(before, self.folder_item_count(), "no Eagle mutation")
        return CaseResult(
            "boundary_short_circuit",
            True,
            "invalid args fail before Eagle/network access",
            result,
        )

    def case_failure_retry(self) -> CaseResult:
        item = self.add_test_item("retry")
        with VisionStub(failures_before_success=1) as stub:
            result = self.moodtag(
                [
                    "tag",
                    "--board",
                    self.folder.id,
                    "--write",
                    "--limit",
                    "1",
                    "--image-edge",
                    "256",
                    "--retries",
                    "1",
                ],
                vision_base_url=stub.base_url,
            )
            assert_ok(result, "retry tag should succeed")
            assert_equal(len(stub.requests), 2, "retry request count")
        updated = self.eagle.item_info(item.id)
        assert_true(moodtag.has_moodboard_notes(updated.annotation), "retry wrote notes")
        return CaseResult(
            "failure_retry",
            True,
            "one transient model failure was retried and then written",
            result,
        )

    def case_severe_empty_result(self) -> CaseResult:
        item = self.add_test_item("empty-result")
        with VisionStub(empty_result=True) as stub:
            result = self.moodtag(
                [
                    "tag",
                    "--board",
                    self.folder.id,
                    "--write",
                    "--limit",
                    "1",
                    "--image-edge",
                    "256",
                    "--retries",
                    "0",
                ],
                vision_base_url=stub.base_url,
            )
            assert_equal(result.returncode, 1, "empty result exit")
            assert_equal(len(stub.requests), 1, "empty result request count")
            assert_in("VL result missing required field: brief", result.stdout, "failure text")
        current = self.eagle.item_info(item.id)
        assert_true(
            not moodtag.has_moodboard_notes(current.annotation),
            "empty result is not written",
        )
        assert_true("photo" not in current.tags, "empty result writes no tags")
        return CaseResult(
            "severe_empty_result",
            True,
            "empty model result is treated as severe failure with no write",
            result,
        )

    def moodtag(
        self, args: list[str], *, vision_base_url: str | None = None
    ) -> CommandResult:
        env = os.environ.copy()
        env.update(
            {
                "MOODTAG_EAGLE_API": self.eagle_api,
                "MOODTAG_API_KEY": E2E_API_KEY,
                "MOODTAG_MODEL": E2E_MODEL,
                "MOODTAG_RETRIES": "0",
            }
        )
        if vision_base_url:
            env["MOODTAG_BASE_URL"] = vision_base_url
        started = time.monotonic()
        proc = subprocess.run(
            [self.python, str(ROOT / "moodtag.py"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return CommandResult(
            args=args,
            returncode=proc.returncode,
            stdout=moodtag.redact(proc.stdout),
            stderr=moodtag.redact(proc.stderr),
            duration_s=round(time.monotonic() - started, 3),
        )

    def add_test_item(self, label: str) -> moodtag.EagleItem:
        name = f"{ITEM_PREFIX}{label}-{int(time.time() * 1000)}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{name}.png"
            write_test_image(path)
            data = moodtag.http_request(
                "POST",
                moodtag.url_join(self.eagle_api, "/api/item/addFromPath"),
                json_body={
                    "path": str(path),
                    "name": name,
                    "folderId": self.folder.id,
                    "annotation": f"e2e source {label}",
                },
                timeout=30,
            )
            moodtag.EagleClient._expect_success(data, "item addFromPath")
            item = self.wait_for_item(name)
            self.created_item_ids.add(item.id)
            return item

    def wait_for_item(self, name: str, *, timeout_s: float = 10) -> moodtag.EagleItem:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for item in self.eagle.list_items(self.folder.id):
                if item.name == name:
                    return item
            time.sleep(0.25)
        raise E2EFailure(f"created Eagle item did not appear: {name}")

    def folder_item_count(self) -> int:
        return len(self.eagle.list_items(self.folder.id))

    def cleanup_test_items(self) -> None:
        ids = [
            item.id
            for item in self.eagle.list_items(self.folder.id)
            if item.name.startswith(ITEM_PREFIX)
        ]
        if not ids:
            return
        moodtag.http_request(
            "POST",
            moodtag.url_join(self.eagle_api, "/api/item/moveToTrash"),
            json_body={"itemIds": ids},
            timeout=10,
        )
        self.created_item_ids.difference_update(ids)


def write_test_image(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        path.write_bytes(base64.b64decode(PNG_1X1))
        return
    image = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, 140, 216), fill=(220, 52, 44))
    draw.ellipse((168, 44, 300, 196), fill=(38, 108, 210))
    draw.line((0, 239, 319, 0), fill=(40, 40, 40), width=4)
    image.save(path, format="PNG")


def assert_ok(result: CommandResult, label: str) -> None:
    if result.returncode != 0:
        raise E2EFailure(
            f"{label}: exit {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise E2EFailure(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(condition: bool, label: str) -> None:
    if not condition:
        raise E2EFailure(label)


def assert_in(needle: str, haystack: str, label: str) -> None:
    if needle not in haystack:
        raise E2EFailure(f"{label}: missing {needle!r} in {haystack!r}")


def write_report(results: list[CaseResult], *, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"moodtag-e2e-{stamp}.json"
    payload = {
        "passed": all(result.passed for result in results),
        "cases": [
            {
                "name": result.name,
                "passed": result.passed,
                "detail": result.detail,
                "command": command_to_dict(result.command),
            }
            for result in results
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def command_to_dict(command: CommandResult | None) -> dict[str, Any] | None:
    if command is None:
        return None
    return {
        "args": command.args,
        "returncode": command.returncode,
        "duration_s": command.duration_s,
        "stdout": command.stdout[-1200:],
        "stderr": command.stderr[-1200:],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="e2e_moodtag")
    parser.add_argument("--eagle-api", default=moodtag.DEFAULT_EAGLE_API)
    parser.add_argument("--board", default=os.environ.get("MOODTAG_E2E_BOARD", ""))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--report-dir", default=str(ROOT / "e2e-results"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite = E2E(eagle_api=args.eagle_api, python=args.python, board_query=args.board)
    print(f"E2E board: {suite.folder.path} ({suite.folder.id})")
    results = suite.run()
    report = write_report(results, output_dir=Path(args.report_dir))
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status}\t{result.name}\t{result.detail}")
    print(f"Report: {report}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
