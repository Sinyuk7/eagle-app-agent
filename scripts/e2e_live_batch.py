#!/usr/bin/env python3
"""Live batch E2E against Eagle and a real OpenAI-compatible vision gateway."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import moodtag  # noqa: E402

DEFAULT_BOARD = "明日方舟 - 小红书"
DEFAULT_FIRST_LIMIT = 5
DEFAULT_LIVE_MODEL = "qwen3.5-122b-a10b"


@dataclass
class RunResult:
    label: str
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    changed: int | None
    skipped: int | None
    failed: int | None


def redact(text: str) -> str:
    return moodtag.redact(text)


def parse_count(label: str, stdout: str) -> int | None:
    prefix = f"{label}:"
    for line in stdout.splitlines():
        if line.startswith(prefix):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def run_moodtag(args: list[str], env: dict[str, str], *, label: str) -> RunResult:
    started = time.monotonic()
    proc = subprocess.run(
        [env.get("MOODTAG_PYTHON", sys.executable), "-m", "moodtag", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = redact(proc.stdout)
    stderr = redact(proc.stderr)
    return RunResult(
        label=label,
        args=args,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_s=round(time.monotonic() - started, 3),
        changed=parse_count("Changed", stdout),
        skipped=parse_count("Skipped", stdout),
        failed=parse_count("Failed", stdout),
    )


def resolve_board(client: moodtag.EagleClient, query: str) -> moodtag.Board:
    return moodtag.resolve_board(query, client.boards())


def board_state(client: moodtag.EagleClient, board: moodtag.Board) -> dict[str, Any]:
    items = client.list_items(board.id)
    processed = [item for item in items if moodtag.has_moodboard_notes(item.annotation)]
    return {
        "board_id": board.id,
        "board_path": board.path,
        "items": len(items),
        "processed": len(processed),
        "pending": len(items) - len(processed),
        "item_ids": [item.id for item in items],
        "processed_ids": [item.id for item in processed],
    }


def find_models(base_url: str, api_key: str) -> list[str]:
    data = moodtag.http_request(
        "GET",
        moodtag.models_url(base_url),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=30,
    )
    models = [
        str(item.get("id"))
        for item in data.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return models


def choose_model(models: list[str]) -> str:
    preferred = [
        model
        for model in models
        if any(token in model.lower() for token in ("vl", "vision", "gpt-4o"))
    ]
    return (preferred or models)[0] if models else ""


def preflight(
    client: moodtag.EagleClient,
    board: moodtag.Board,
    *,
    base_url: str,
    fallback_base_url: str,
    model: str,
    api_key: str,
    taxonomy_path: Path,
    image_edge: int,
    no_response_format: bool,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> dict[str, Any]:
    taxonomy = moodtag.load_taxonomy(taxonomy_path)
    pending = [
        item
        for item in client.list_items(board.id)
        if not moodtag.has_moodboard_notes(item.annotation)
    ]
    if not pending:
        raise moodtag.MoodtagError("No pending item available for live preflight")
    item = pending[0]
    thumbnail = client.thumbnail_path(item.id)
    original = moodtag.locate_original_from_thumbnail(thumbnail, item)
    vision = moodtag.VisionClient(
        base_url=base_url,
        fallback_base_url=fallback_base_url,
        model=model,
        api_key=api_key,
        response_format=not no_response_format,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    with moodtag.temporary_preview(original, image_edge=image_edge) as preview:
        result = vision.analyze(preview.path, taxonomy, retries=0, max_tags=15)
    moodtag.validate_vl_result(result)
    tags, rejected = moodtag.reconcile_tags(result, taxonomy, max_tags=15)
    return {
        "item_id": item.id,
        "item_name": item.name,
        "brief": result.brief,
        "elements": result.elements,
        "tags": tags,
        "rejected_tags": rejected,
        "use_intents": result.use_intents,
    }


def assert_run(
    result: RunResult,
    *,
    returncode: int,
    changed: int | None = None,
    skipped: int | None = None,
    failed: int | None = None,
) -> None:
    if result.returncode != returncode:
        raise moodtag.MoodtagError(
            f"{result.label} exited {result.returncode}, expected {returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    for name, actual, expected in (
        ("Changed", result.changed, changed),
        ("Skipped", result.skipped, skipped),
        ("Failed", result.failed, failed),
    ):
        if expected is not None and actual != expected:
            raise moodtag.MoodtagError(
                f"{result.label} {name} expected {expected}, got {actual}"
            )


def write_report(payload: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"moodtag-live-batch-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fail_with_report(payload: dict[str, Any], report_dir: Path) -> int:
    payload["passed"] = False
    report = write_report(payload, report_dir)
    print(
        f"FAIL live_batch {payload.get('failure', 'unknown failure')}", file=sys.stderr
    )
    print(f"Report: {report}", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="e2e_live_batch")
    parser.add_argument(
        "--board", default=os.environ.get("MOODTAG_E2E_BOARD", DEFAULT_BOARD)
    )
    parser.add_argument(
        "--eagle-api",
        default=os.environ.get("MOODTAG_EAGLE_API", moodtag.DEFAULT_EAGLE_API),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MOODTAG_BASE_URL", moodtag.DEFAULT_BASE_URL),
    )
    parser.add_argument(
        "--fallback-base-url",
        default=os.environ.get(
            "MOODTAG_FALLBACK_BASE_URL", moodtag.DEFAULT_FALLBACK_BASE_URL
        ),
    )
    parser.add_argument(
        "--model", default=os.environ.get("MOODTAG_MODEL", DEFAULT_LIVE_MODEL)
    )
    parser.add_argument("--discover-models", action="store_true")
    parser.add_argument(
        "--taxonomy",
        default=os.environ.get("MOODTAG_TAXONOMY", moodtag.DEFAULT_TAXONOMY),
    )
    parser.add_argument(
        "--image-edge",
        type=int,
        default=env_int("MOODTAG_IMAGE_EDGE", moodtag.DEFAULT_IMAGE_EDGE),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=env_float("MOODTAG_TEMPERATURE", moodtag.DEFAULT_TEMPERATURE),
    )
    parser.add_argument(
        "--top-p", type=float, default=env_float("MOODTAG_TOP_P", moodtag.DEFAULT_TOP_P)
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=env_int("MOODTAG_MAX_TOKENS", moodtag.DEFAULT_MAX_TOKENS),
    )
    parser.add_argument("--first-limit", type=int, default=DEFAULT_FIRST_LIMIT)
    parser.add_argument("--min-items", type=int, default=10)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--reset-first", action="store_true")
    parser.add_argument(
        "--no-response-format",
        action="store_true",
        default=moodtag.DEFAULT_NO_RESPONSE_FORMAT,
    )
    parser.add_argument(
        "--response-format",
        dest="no_response_format",
        action="store_false",
        default=argparse.SUPPRESS,
    )
    parser.add_argument("--report-dir", default=str(ROOT / "e2e-results"))
    return parser.parse_args()


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    return int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    return float(raw)


def main() -> int:
    moodtag.load_env_defaults()
    args = parse_args()
    api_key = os.environ.get("MOODTAG_API_KEY") or os.environ.get("VL_API_KEY")
    if not api_key:
        raise SystemExit("MOODTAG_API_KEY or VL_API_KEY is required")

    report_dir = Path(args.report_dir)
    client = moodtag.EagleClient(args.eagle_api)
    board = resolve_board(client, args.board)
    initial = board_state(client, board)
    payload: dict[str, Any] = {
        "passed": False,
        "board": {"id": board.id, "path": board.path},
        "base_url": args.base_url,
        "fallback_base_url": args.fallback_base_url,
        "model": args.model,
        "models": [],
        "states": {"initial": initial},
        "runs": [],
    }
    if not (args.min_items <= initial["items"] <= args.max_items):
        payload["failure"] = (
            f"Board must contain {args.min_items}-{args.max_items} items; "
            f"got {initial['items']} in {board.path}"
        )
        return fail_with_report(payload, report_dir)

    model = args.model
    models: list[str] = []
    if args.discover_models or not model:
        models = find_models(args.base_url, api_key)
        if not model:
            model = choose_model(models)
    payload["models"] = models
    payload["model"] = model
    if not model:
        payload["failure"] = "No model configured and /v1/models returned no models"
        return fail_with_report(payload, report_dir)

    env = os.environ.copy()
    env.update(
        {
            "MOODTAG_EAGLE_API": args.eagle_api,
            "MOODTAG_BASE_URL": args.base_url,
            "MOODTAG_FALLBACK_BASE_URL": args.fallback_base_url,
            "MOODTAG_MODEL": model,
            "MOODTAG_API_KEY": api_key,
            "MOODTAG_TAXONOMY": args.taxonomy,
            "MOODTAG_IMAGE_EDGE": str(args.image_edge),
            "MOODTAG_TEMPERATURE": str(args.temperature),
            "MOODTAG_TOP_P": str(args.top_p),
            "MOODTAG_MAX_TOKENS": str(args.max_tokens),
            "MOODTAG_NO_RESPONSE_FORMAT": "true"
            if args.no_response_format
            else "false",
        }
    )

    runs: list[RunResult] = []
    if args.reset_first:
        runs.append(
            run_moodtag(
                ["reset", "--board", board.id, "--write"],
                env,
                label="reset_first",
            )
        )
        assert_run(runs[-1], returncode=0)
        initial = board_state(client, board)
        payload["states"]["after_reset_first"] = initial
        if initial["processed"] != 0 or initial["pending"] != initial["items"]:
            raise moodtag.MoodtagError(
                f"Reset-first did not clear board processing state: {initial}"
            )

    try:
        preflight_result = preflight(
            client,
            board,
            base_url=args.base_url,
            fallback_base_url=args.fallback_base_url,
            model=model,
            api_key=api_key,
            taxonomy_path=Path(args.taxonomy),
            image_edge=args.image_edge,
            no_response_format=args.no_response_format,
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - report live gateway failures
        payload["failure"] = "live preflight failed"
        payload["preflight_error"] = redact(str(exc))
        payload["states"]["after_preflight_failure"] = board_state(client, board)
        return fail_with_report(payload, report_dir)

    if args.preflight_only:
        payload.update(
            {
                "passed": True,
                "preflight_only": True,
                "preflight": preflight_result,
                "states": {
                    "initial": initial,
                    "final": board_state(client, board),
                },
            }
        )
        report = write_report(payload, report_dir)
        print(
            f"PASS live_preflight board={board.path} "
            f"items={initial['items']} model={model}"
        )
        print(f"brief={preflight_result['brief']}")
        print(f"Report: {report}")
        return 0

    first_limit = min(args.first_limit, initial["pending"])
    if first_limit <= 0:
        raise SystemExit("Board has no pending items before interrupt simulation")

    common_tag_args = [
        "tag",
        "--board",
        board.id,
        "--write",
        "--image-edge",
        str(args.image_edge),
    ]
    if args.no_response_format:
        common_tag_args.append("--no-response-format")

    runs.append(
        run_moodtag(
            [*common_tag_args, "--limit", str(first_limit)],
            env,
            label="interrupt_first_partial",
        )
    )
    assert_run(runs[-1], returncode=0, changed=first_limit, skipped=0, failed=0)
    after_partial = board_state(client, board)

    runs.append(run_moodtag(common_tag_args, env, label="resume_full"))
    expected_remaining = initial["items"] - first_limit
    assert_run(
        runs[-1],
        returncode=0,
        changed=expected_remaining,
        skipped=first_limit,
        failed=0,
    )
    after_resume = board_state(client, board)

    runs.append(run_moodtag(common_tag_args, env, label="repeat_full"))
    assert_run(runs[-1], returncode=0, changed=0, skipped=initial["items"], failed=0)
    final = board_state(client, board)

    if final["processed"] != initial["items"] or final["pending"] != 0:
        raise moodtag.MoodtagError(f"Final board state mismatch: {final}")

    payload.update(
        {
            "passed": True,
            "board": {"id": board.id, "path": board.path},
            "base_url": args.base_url,
            "fallback_base_url": args.fallback_base_url,
            "model": model,
            "models": models,
            "preflight": preflight_result,
            "states": {
                "initial": initial,
                "after_partial": after_partial,
                "after_resume": after_resume,
                "final": final,
            },
            "runs": [run.__dict__ for run in runs],
        }
    )
    report = write_report(payload, report_dir)
    print(f"PASS live_batch board={board.path} items={initial['items']} model={model}")
    print(
        f"partial changed={first_limit}; resume changed={expected_remaining}; "
        f"repeat skipped={initial['items']}"
    )
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except moodtag.MoodtagError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        raise SystemExit(1) from exc
