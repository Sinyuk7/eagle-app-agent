#!/usr/bin/env python3
"""Create a moodboard project directory and starter index.html."""

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from importlib import resources
from pathlib import Path


def clean_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r'[\/\\:*?"<>|\x00-\x1f]', "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-. ")
    return value or "未命名项目"


def default_template_path() -> Path:
    return Path(
        str(
            resources.files("moodboard_core.resources.templates").joinpath(
                "starter.html"
            )
        )
    )


def render_template(template_path: Path, project_name: str) -> str:
    text = template_path.read_text(encoding="utf-8")
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    project_id = hashlib.sha1(f"{project_name}|{created_at}".encode()).hexdigest()[:12]
    replacements = {
        "PROJECT_TITLE": project_name,
        "PROJECT_DIR_NAME": project_name,
        "PROJECT_ID": project_id,
        "PROJECT_CREATED_AT": created_at,
        "PROJECT_CREATED_DATE": created_at[:10],
        "PROJECT_UPDATED_AT": created_at,
    }
    for key, value in replacements.items():
        text = text.replace(f"{{{{{key}}}}}", html.escape(value))
    return text


def project_state(project_name: str, base: Path, template_path: Path) -> dict:
    project_dir = base / project_name
    index_path = project_dir / "index.html"
    return {
        "project_name": project_name,
        "base": str(base),
        "project_dir": str(project_dir),
        "index_html": str(index_path),
        "template": str(template_path),
        "project_exists": project_dir.exists(),
        "index_exists": index_path.exists(),
        "template_exists": template_path.exists(),
    }


def unique_project_name(project_name: str, base: Path) -> tuple[str, bool]:
    if not (base / project_name).exists():
        return project_name, False
    index = 1
    while True:
        candidate = f"{project_name}_{index:02d}"
        if not (base / candidate).exists():
            return candidate, True
        index += 1


def backup_path_for(project_dir: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    candidate = project_dir.with_name(f"{project_dir.name}.backup-{stamp}")
    suffix = 2
    while candidate.exists():
        candidate = project_dir.with_name(f"{project_dir.name}.backup-{stamp}-{suffix}")
        suffix += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", help="Confirmed project directory name")
    parser.add_argument(
        "--base", default="~/Documents/Moodboard", help="Moodboard base directory"
    )
    parser.add_argument(
        "--template", default=str(default_template_path()), help="Starter HTML template"
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow using an existing project directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report cleaned name and target state without writing files",
    )
    parser.add_argument(
        "--backup-existing",
        action="store_true",
        help="Rename an existing project directory to a timestamped backup before creating",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete an existing project directory and recreate it",
    )
    args = parser.parse_args(argv)

    selected_modes = sum(
        bool(v) for v in (args.dry_run, args.backup_existing, args.overwrite)
    )
    if selected_modes > 1:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "conflicting_modes",
                    "message": "Use only one of --dry-run, --backup-existing, or --overwrite",
                },
                ensure_ascii=False,
            )
        )
        return 2

    base = Path(args.base).expanduser()
    template_path = Path(args.template).expanduser()
    requested_project_name = clean_name(args.project_name)
    if args.dry_run or args.allow_existing or args.backup_existing or args.overwrite:
        project_name = requested_project_name
        deduped = False
    else:
        project_name, deduped = unique_project_name(requested_project_name, base)
    project_dir = base / project_name
    index_path = project_dir / "index.html"
    state = project_state(project_name, base, template_path)

    if args.dry_run:
        unique_name, dry_run_deduped = unique_project_name(requested_project_name, base)
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "requested_project_name": requested_project_name,
                    "deduped": dry_run_deduped,
                    **project_state(unique_name, base, template_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not template_path.exists():
        print(
            json.dumps(
                {"ok": False, "error": "missing_template", **state}, ensure_ascii=False
            )
        )
        return 2

    backup_dir = None
    overwritten = False
    if project_dir.exists() and args.backup_existing:
        backup_dir = backup_path_for(project_dir)
        project_dir.rename(backup_dir)
    elif project_dir.exists() and args.overwrite:
        shutil.rmtree(project_dir)
        overwritten = True
    elif project_dir.exists() and not args.allow_existing:
        print(
            json.dumps(
                {"ok": False, "error": "project_exists", **state}, ensure_ascii=False
            )
        )
        return 2

    project_dir.mkdir(parents=True, exist_ok=True)
    if index_path.exists() and not args.allow_existing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "index_exists",
                    **project_state(project_name, base, template_path),
                    "backup_dir": str(backup_dir) if backup_dir else None,
                    "overwritten": overwritten,
                    "overwrote": overwritten,
                },
                ensure_ascii=False,
            )
        )
        return 2

    created_index = not index_path.exists()
    if created_index:
        index_path.write_text(
            render_template(template_path, project_name), encoding="utf-8"
        )

    print(
        json.dumps(
            {
                "ok": True,
                "requested_project_name": requested_project_name,
                "deduped": deduped,
                **project_state(project_name, base, template_path),
                "created_index": created_index,
                "backup_dir": str(backup_dir) if backup_dir else None,
                "overwritten": overwritten,
                "overwrote": overwritten,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
