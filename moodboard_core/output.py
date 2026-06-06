from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import body as body_core
from . import check as check_core


def run_json_command(
    func: Callable[[list[str]], int], argv: list[str]
) -> tuple[int, dict[str, Any], str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = func(argv)
    stdout = buffer.getvalue()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": "invalid_json", "stdout": stdout}
    return code, payload, stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write and validate the final moodboard index.html"
    )
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--index", default="")
    parser.add_argument("--body-file", default="")
    parser.add_argument("--no-process-images", action="store_true")
    parser.add_argument(
        "--local-image-mode", choices=["symlink", "copy"], default="symlink"
    )
    parser.add_argument("--cache-dir", default="assets/references")
    parser.add_argument("--localhost-mode", action="store_true")
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser()
    index_path = (
        Path(args.index).expanduser() if args.index else project_dir / "index.html"
    )
    body_argv = [
        str(index_path),
        "--project-dir",
        str(project_dir),
        "--touch-updated-at",
        "--local-image-mode",
        args.local_image_mode,
        "--cache-dir",
        args.cache_dir,
    ]
    if args.body_file:
        body_argv.extend(["--body-file", args.body_file])
    if args.no_process_images:
        body_argv.append("--no-process-images")

    body_code, body_payload, _body_stdout = run_json_command(body_core.main, body_argv)
    if body_code != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "body_apply_failed",
                    "project_dir": str(project_dir),
                    "index_html": str(index_path),
                    "body": body_payload,
                },
                ensure_ascii=False,
            )
        )
        return body_code

    check_argv = [str(project_dir), "--check-assets", "--check-links"]
    if args.localhost_mode:
        check_argv.append("--localhost-mode")
    check_code, check_payload, _check_stdout = run_json_command(
        check_core.main, check_argv
    )
    if check_code != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "check_failed",
                    "project_dir": str(project_dir),
                    "index_html": str(index_path),
                    "body": body_payload,
                    "image_processing": body_payload.get("image_processing"),
                    "check": check_payload,
                },
                ensure_ascii=False,
            )
        )
        return check_code

    print(
        json.dumps(
            {
                "ok": True,
                "project_dir": str(project_dir),
                "index_html": str(index_path),
                "body": body_payload,
                "image_processing": body_payload.get("image_processing"),
                "check": check_payload,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
