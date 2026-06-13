from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from moodboard_core import body as body_core
from moodboard_core import check as check_core
from moodboard_core import layout as layout_core
from moodboard_core import output as output_core
from moodboard_core import project as project_core
from moodboard_core import serve as serve_core
from moodboard_core.resources_api import get_resource


def emit_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def command_resources_get(args: argparse.Namespace) -> int:
    try:
        resources = [get_resource(name) for name in args.names]
    except ValueError as exc:
        emit_json({"ok": False, "error": "unknown_resource", "message": str(exc)})
        return 2
    payload = {
        "ok": True,
        "resources": [
            {"name": item.name, "path": item.path, "content": item.content}
            for item in resources
        ],
    }
    if args.json:
        emit_json(payload)
        return 0
    if len(resources) != 1:
        emit_json({"ok": False, "error": "multiple_resources_require_json"})
        return 2
    sys.stdout.write(resources[0].content)
    return 0


def command_project_preflight(args: argparse.Namespace) -> int:
    argv = [args.name, "--base", args.base, "--dry-run"]
    if args.template:
        argv.extend(["--template", args.template])
    return project_core.main(argv)


def command_project_create(args: argparse.Namespace) -> int:
    argv = [args.name, "--base", args.base]
    if args.template:
        argv.extend(["--template", args.template])
    if args.allow_existing:
        argv.append("--allow-existing")
    if args.backup_existing:
        argv.append("--backup-existing")
    if args.overwrite:
        argv.append("--overwrite")
    return project_core.main(argv)


def command_body_apply(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).expanduser()
    index_path = (
        Path(args.index).expanduser() if args.index else project_dir / "index.html"
    )
    argv = [str(index_path), "--project-dir", str(project_dir)]
    if args.body_file:
        argv.extend(["--body-file", args.body_file])
    if args.touch_updated_at:
        argv.append("--touch-updated-at")
    if args.no_process_images:
        argv.append("--no-process-images")
    if args.local_image_mode:
        argv.extend(["--local-image-mode", args.local_image_mode])
    if args.cache_dir:
        argv.extend(["--cache-dir", args.cache_dir])
    return body_core.main(argv)


def command_check(args: argparse.Namespace) -> int:
    argv = [args.path]
    if args.allow_empty_body:
        argv.append("--allow-empty-body")
    if args.check_assets:
        argv.append("--check-assets")
    if args.check_links:
        argv.append("--check-links")
    if args.network_assets:
        argv.append("--network-assets")
    if args.localhost_mode:
        argv.append("--localhost-mode")
    return check_core.main(argv)


def command_output_write(args: argparse.Namespace) -> int:
    argv = ["--project-dir", args.project_dir]
    if args.index:
        argv.extend(["--index", args.index])
    if args.body_file:
        argv.extend(["--body-file", args.body_file])
    if args.no_process_images:
        argv.append("--no-process-images")
    if args.local_image_mode:
        argv.extend(["--local-image-mode", args.local_image_mode])
    if args.cache_dir:
        argv.extend(["--cache-dir", args.cache_dir])
    if args.localhost_mode:
        argv.append("--localhost-mode")
    return output_core.main(argv)


def command_serve(args: argparse.Namespace) -> int:
    argv = [args.project_dir, "--host", args.host, "--port", str(args.port)]
    if args.preflight_localhost:
        argv.append("--preflight-localhost")
    return serve_core.main(argv)


def command_layout(args: argparse.Namespace) -> int:
    return layout_core.main(args.layout_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moodboard", description="Local moodboard HTML project runtime"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    resources = sub.add_parser("resources", help="Read bundled moodboard resources")
    resources_sub = resources.add_subparsers(dest="resources_command", required=True)
    resources_get = resources_sub.add_parser(
        "get", help="Read one or more bundled resources"
    )
    resources_get.add_argument("names", nargs="+")
    resources_get.add_argument(
        "--json", action="store_true", help="Return resource content as JSON"
    )
    resources_get.set_defaults(func=command_resources_get)

    project = sub.add_parser(
        "project", help="Create and inspect moodboard project directories"
    )
    project_sub = project.add_subparsers(dest="project_command", required=True)
    preflight = project_sub.add_parser(
        "preflight", help="Report target project state without writing"
    )
    preflight.add_argument("--name", required=True)
    preflight.add_argument("--base", default="~/Documents/Moodboard")
    preflight.add_argument("--template", default="")
    preflight.set_defaults(func=command_project_preflight)
    create = project_sub.add_parser(
        "create", help="Create or prepare a moodboard project"
    )
    create.add_argument("--name", required=True)
    create.add_argument("--base", default="~/Documents/Moodboard")
    create.add_argument("--template", default="")
    create.add_argument("--allow-existing", action="store_true")
    create.add_argument("--backup-existing", action="store_true")
    create.add_argument("--overwrite", action="store_true")
    create.set_defaults(func=command_project_create)

    body = sub.add_parser("body", help="Apply body-only HTML to a moodboard project")
    body_sub = body.add_subparsers(dest="body_command", required=True)
    apply = body_sub.add_parser(
        "apply", help="Replace body content and normalize local image references"
    )
    apply.add_argument("--project-dir", required=True)
    apply.add_argument("--index", default="")
    apply.add_argument("--body-file", default="")
    apply.add_argument("--touch-updated-at", action="store_true")
    apply.add_argument("--no-process-images", action="store_true")
    apply.add_argument(
        "--local-image-mode", choices=["symlink", "copy"], default="symlink"
    )
    apply.add_argument("--cache-dir", default="assets/references")
    apply.set_defaults(func=command_body_apply)

    check = sub.add_parser("check", help="Check moodboard HTML")
    check.add_argument("path")
    check.add_argument("--allow-empty-body", action="store_true")
    check.add_argument("--check-assets", action="store_true")
    check.add_argument("--check-links", action="store_true")
    check.add_argument("--network-assets", action="store_true")
    check.add_argument("--localhost-mode", action="store_true")
    check.set_defaults(func=command_check)

    output = sub.add_parser(
        "output", help="Write and validate moodboard output artifacts"
    )
    output_sub = output.add_subparsers(dest="output_command", required=True)
    output_write = output_sub.add_parser(
        "write", help="Write body HTML and validate index.html"
    )
    output_write.add_argument("--project-dir", required=True)
    output_write.add_argument("--index", default="")
    output_write.add_argument("--body-file", default="")
    output_write.add_argument("--no-process-images", action="store_true")
    output_write.add_argument(
        "--local-image-mode", choices=["symlink", "copy"], default="symlink"
    )
    output_write.add_argument("--cache-dir", default="assets/references")
    output_write.add_argument("--localhost-mode", action="store_true")
    output_write.set_defaults(func=command_output_write)

    serve = sub.add_parser("serve", help="Serve a moodboard project on localhost")
    serve.add_argument("project_dir")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--preflight-localhost", action="store_true")
    serve.set_defaults(func=command_serve)

    layout = sub.add_parser(
        "layout", help="Compute deterministic image specs and geometry plans"
    )
    layout.add_argument("layout_args", nargs=argparse.REMAINDER)
    layout.set_defaults(func=command_layout)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
