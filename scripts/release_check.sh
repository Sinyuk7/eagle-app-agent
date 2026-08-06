#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_CMD=("$PYTHON")
else
  PYTHON_CMD=(uv run python)
fi

"${PYTHON_CMD[@]}" -m unittest discover -s tests

rm -rf dist build
uv build --no-sources

uv run --no-project --with twine -- python -m twine check dist/*
uv run --no-project --with "dist/eagle_app_agent-"*.whl -- moodtag --help >/dev/null

if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  OUTPUT_DIR="$ROOT/dist/macos" packaging/macos/build_installer.sh
  packaging/macos/smoke_check.sh "$ROOT"/dist/macos/*.pkg
else
  echo "Skipping macOS installer build: requires an arm64 macOS host."
fi
