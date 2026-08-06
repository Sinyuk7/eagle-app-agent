#!/usr/bin/env bash
set -euo pipefail

INSTALL=0
PACKAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      INSTALL=1
      shift
      ;;
    --package)
      PACKAGE="${2:-}"
      shift 2
      ;;
    *)
      if [[ -z "$PACKAGE" ]]; then
        PACKAGE="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        exit 2
      fi
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "macOS arm64 smoke check requires an arm64 macOS runner." >&2
  exit 1
fi
if [[ -z "$PACKAGE" || ! -f "$PACKAGE" ]]; then
  echo "Usage: $0 [--install] <path-to-pkg>" >&2
  exit 2
fi

PAYLOAD="$(pkgutil --payload-files "$PACKAGE" | sed 's#^\./##')"
grep -Fxq "usr/local/libexec/moodtag/moodtag" <<<"$PAYLOAD"
grep -Fxq "usr/local/bin/moodtag" <<<"$PAYLOAD"

PACKAGE_PARENT="$(mktemp -d "${TMPDIR:-/tmp}/moodtag-package.XXXXXX")"
EXPANDED_ROOT="$PACKAGE_PARENT/expanded"
SMOKE_HOME="$(mktemp -d "${TMPDIR:-/tmp}/moodtag-smoke.XXXXXX")"
trap 'rm -rf "$PACKAGE_PARENT" "$SMOKE_HOME"' EXIT
pkgutil --expand-full "$PACKAGE" "$EXPANDED_ROOT"
COMMAND_PATH="$EXPANDED_ROOT/Payload/usr/local/bin/moodtag"

if [[ "$INSTALL" -eq 1 ]]; then
  INSTALLER=(/usr/sbin/installer -pkg "$PACKAGE" -target /)
  if [[ "$(id -u)" -eq 0 ]]; then
    "${INSTALLER[@]}"
  else
    sudo "${INSTALLER[@]}"
  fi
  COMMAND_PATH="/usr/local/bin/moodtag"
fi

if [[ ! -x "$COMMAND_PATH" ]]; then
  echo "Installed moodtag command missing at $COMMAND_PATH" >&2
  exit 1
fi

if ! file -L "$COMMAND_PATH" | grep -q "Mach-O"; then
  echo "Installed moodtag command is not a native macOS executable" >&2
  exit 1
fi

env -i HOME="$SMOKE_HOME" PATH="$(dirname "$COMMAND_PATH"):/usr/bin:/bin:/usr/sbin:/sbin" \
  EXPECTED_COMMAND_PATH="$COMMAND_PATH" \
  /bin/zsh -c 'test "$(command -v moodtag)" = "$EXPECTED_COMMAND_PATH" && moodtag --help' \
  >/dev/null

echo "macOS installer smoke check passed: $PACKAGE"
