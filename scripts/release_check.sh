#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON:-python}"

"$PYTHON_BIN" -m unittest discover -s tests

rm -rf dist build
uv build --no-sources

uv run --no-project --with twine -- python -m twine check dist/*
uv run --no-project --with "dist/eagle_app_agent-"*.whl -- moodtag --help >/dev/null
