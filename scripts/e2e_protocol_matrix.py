#!/usr/bin/env python3
"""Run destructive live E2E checks for the configured protocol matrix."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moodtag_core.provider import protocol_url  # noqa: E402

DEFAULT_BOARD = "http://localhost:41595/folder?id=MSHGWFME8L6SJ"


@dataclass(frozen=True)
class LiveProfile:
    name: str
    protocol: str
    base_url: str
    model: str
    api_key_env: str

    @property
    def endpoint_url(self) -> str:
        return protocol_url(self.base_url, self.protocol)


PROFILES = (
    LiveProfile(
        name="responses-gpt-5.6-luna",
        protocol="responses",
        base_url="https://sub2.de5.net",
        model="gpt-5.6-luna",
        api_key_env="MOODTAG_E2E_RESPONSES_API_KEY",
    ),
    LiveProfile(
        name="chat-qwen3.5-122b-a10b",
        protocol="chat",
        base_url="https://llm-api.net/v1",
        model="qwen3.5-122b-a10b",
        api_key_env="MOODTAG_E2E_CHAT_API_KEY",
    ),
)


class MatrixError(RuntimeError):
    """Expected live-matrix validation failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="e2e_protocol_matrix")
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument(
        "--confirm-reset",
        default="",
        metavar="FOLDER_ID",
        help="Required confirmation because each profile clears all tags and annotations",
    )
    parser.add_argument(
        "--only",
        choices=("all", "responses", "chat"),
        default="all",
    )
    parser.add_argument("--first-limit", type=int, default=2)
    parser.add_argument("--min-items", type=int, default=1)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument(
        "--report-dir", default=str(ROOT / "e2e-results" / "protocol-matrix")
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print public test configuration without reading credentials or contacting services",
    )
    return parser.parse_args()


def selected_profiles(choice: str) -> tuple[LiveProfile, ...]:
    if choice == "all":
        return PROFILES
    return tuple(profile for profile in PROFILES if profile.protocol == choice)


def folder_id(board: str) -> str:
    value = str(board or "").strip()
    parts = urllib.parse.urlsplit(value)
    if parts.scheme and parts.netloc:
        return urllib.parse.parse_qs(parts.query).get("id", [""])[0].strip()
    return value


def redact(text: str, secrets: list[str]) -> str:
    value = str(text)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "REDACTED")
    return re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-REDACTED", value)


def profile_command(profile: LiveProfile, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "e2e_live_batch.py"),
        "--board",
        args.board,
        "--protocol",
        profile.protocol,
        "--base-url",
        profile.base_url,
        "--model",
        profile.model,
        "--first-limit",
        str(args.first_limit),
        "--min-items",
        str(args.min_items),
        "--max-items",
        str(args.max_items),
        "--reset-first",
        "--report-dir",
        str(Path(args.report_dir) / profile.name),
    ]


def report_path(output: str) -> Path:
    for line in reversed(output.splitlines()):
        if line.startswith("Report: "):
            return Path(line.removeprefix("Report: ").strip())
    raise MatrixError("Live profile did not report a result path")


def validate_report(
    profile: LiveProfile,
    path: Path,
    *,
    expected_folder_id: str,
    secrets: list[str],
) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    if any(secret and secret in serialized for secret in secrets):
        raise MatrixError(f"{profile.name} report contains a configured secret")
    expected = {
        "passed": True,
        "protocol": profile.protocol,
        "base_url": profile.base_url,
        "endpoint_url": profile.endpoint_url,
        "model": profile.model,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise MatrixError(
                f"{profile.name} report {key}={payload.get(key)!r}, expected {value!r}"
            )
    board = payload.get("board")
    if not isinstance(board, dict) or board.get("id") != expected_folder_id:
        raise MatrixError(f"{profile.name} report used unexpected Eagle folder")
    states = payload.get("states")
    if not isinstance(states, dict):
        raise MatrixError(f"{profile.name} report has no state timeline")
    initial = states.get("initial")
    final = states.get("final")
    if not isinstance(initial, dict) or not isinstance(final, dict):
        raise MatrixError(f"{profile.name} report has incomplete state timeline")
    item_count = int(initial.get("items") or 0)
    if initial.get("processed") != 0 or final.get("processed") != item_count:
        raise MatrixError(f"{profile.name} reset/write state assertion failed")
    runs = payload.get("runs")
    if not isinstance(runs, list) or [
        run.get("label") for run in runs if isinstance(run, dict)
    ] != [
        "reset_first",
        "interrupt_first_partial",
        "resume_full",
        "repeat_full",
    ]:
        raise MatrixError(f"{profile.name} run sequence assertion failed")
    repeat = runs[-1]
    if (
        not isinstance(repeat, dict)
        or repeat.get("changed") != 0
        or repeat.get("skipped") != item_count
    ):
        raise MatrixError(f"{profile.name} repeat-run skip assertion failed")
    return payload


def run_profile(
    profile: LiveProfile,
    args: argparse.Namespace,
    *,
    api_key: str,
    all_secrets: list[str],
    expected_folder_id: str,
) -> dict[str, object]:
    env = os.environ.copy()
    for configured in PROFILES:
        env.pop(configured.api_key_env, None)
    env["MOODTAG_API_KEY"] = api_key
    started = time.monotonic()
    proc = subprocess.run(
        profile_command(profile, args),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = redact(proc.stdout, all_secrets)
    stderr = redact(proc.stderr, all_secrets)
    combined = "\n".join(value for value in (stdout, stderr) if value)
    if proc.returncode != 0:
        raise MatrixError(
            f"{profile.name} exited {proc.returncode}\n{combined.strip()}"
        )
    path = report_path(combined)
    payload = validate_report(
        profile,
        path,
        expected_folder_id=expected_folder_id,
        secrets=all_secrets,
    )
    return {
        "name": profile.name,
        "protocol": profile.protocol,
        "base_url": profile.base_url,
        "endpoint_url": profile.endpoint_url,
        "model": profile.model,
        "duration_s": round(time.monotonic() - started, 3),
        "report": str(path),
        "items": payload["states"]["final"]["items"],
    }


def write_matrix_report(results: list[dict[str, object]], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"matrix-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(
        json.dumps({"passed": True, "profiles": results}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    args = parse_args()
    profiles = selected_profiles(args.only)
    expected_folder_id = folder_id(args.board)
    if not expected_folder_id:
        raise SystemExit("--board must be a folder ID or URL containing id=")
    if args.plan:
        print(
            json.dumps(
                {
                    "board": args.board,
                    "folder_id": expected_folder_id,
                    "destructive_reset_before_each_profile": True,
                    "profiles": [
                        asdict(profile) | {"endpoint_url": profile.endpoint_url}
                        for profile in profiles
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.confirm_reset != expected_folder_id:
        raise SystemExit(
            f"Refusing destructive reset. Pass --confirm-reset {expected_folder_id}"
        )
    keys = {
        profile.name: os.environ.get(profile.api_key_env, "").strip()
        for profile in profiles
    }
    missing = [profile.api_key_env for profile in profiles if not keys[profile.name]]
    if missing:
        raise SystemExit(
            "Missing required secret environment variables: " + ", ".join(missing)
        )
    all_secrets = list(keys.values())
    results = [
        run_profile(
            profile,
            args,
            api_key=keys[profile.name],
            all_secrets=all_secrets,
            expected_folder_id=expected_folder_id,
        )
        for profile in profiles
    ]
    report = write_matrix_report(results, Path(args.report_dir))
    for result in results:
        print(
            f"PASS {result['name']} endpoint={result['endpoint_url']} "
            f"items={result['items']}"
        )
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MatrixError as exc:
        secrets = [os.environ.get(profile.api_key_env, "") for profile in PROFILES]
        print(f"error: {redact(str(exc), secrets)}", file=sys.stderr)
        raise SystemExit(1) from exc
