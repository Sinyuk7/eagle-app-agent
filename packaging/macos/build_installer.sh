#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml" | head -n 1)"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/dist}"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/moodtag-build.XXXXXX")"
trap 'rm -rf "$BUILD_ROOT"' EXIT

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "moodtag macOS installer requires an arm64 macOS builder (M1-M5)." >&2
  exit 1
fi

if [[ -n "${PYINSTALLER_BIN:-}" ]]; then
  PYINSTALLER_CMD=("$PYINSTALLER_BIN")
elif command -v pyinstaller >/dev/null 2>&1; then
  PYINSTALLER_CMD=(pyinstaller)
elif command -v uv >/dev/null 2>&1; then
  PYINSTALLER_CMD=(uv run --with pyinstaller pyinstaller)
else
  echo "PyInstaller not found. Install it or install uv first." >&2
  exit 1
fi

PYINSTALLER_DIST="$BUILD_ROOT/pyinstaller-dist"
PYINSTALLER_BUILD="$BUILD_ROOT/pyinstaller-build"
mkdir -p "$PYINSTALLER_DIST" "$PYINSTALLER_BUILD" "$OUTPUT_DIR"

"${PYINSTALLER_CMD[@]}" \
  --noconfirm \
  --clean \
  --onefile \
  --name moodtag \
  --target-architecture arm64 \
  --paths "$ROOT" \
  --collect-submodules moodtag_core \
  --collect-data moodtag_core \
  --distpath "$PYINSTALLER_DIST" \
  --workpath "$PYINSTALLER_BUILD" \
  --specpath "$BUILD_ROOT" \
  "$ROOT/packaging/macos/entrypoint.py"

PACKAGE_ROOT="$BUILD_ROOT/package-root"
mkdir -p "$PACKAGE_ROOT/usr/local/libexec/moodtag" "$PACKAGE_ROOT/usr/local/bin"
install -m 755 "$PYINSTALLER_DIST/moodtag" "$PACKAGE_ROOT/usr/local/libexec/moodtag/moodtag"
ln -s ../libexec/moodtag/moodtag "$PACKAGE_ROOT/usr/local/bin/moodtag"

PKG="$OUTPUT_DIR/Moodtag-${VERSION}-macos-arm64.pkg"
DMG="$OUTPUT_DIR/Moodtag-${VERSION}-macos-arm64.dmg"
rm -f "$PKG" "$DMG"

pkgbuild \
  --root "$PACKAGE_ROOT" \
  --identifier com.sinyuk.moodtag \
  --version "$VERSION" \
  --install-location / \
  "$PKG"

DMG_ROOT="$BUILD_ROOT/dmg-root"
mkdir -p "$DMG_ROOT"
cp "$PKG" "$DMG_ROOT/"
cp "$ROOT/packaging/macos/DMG-README.txt" "$DMG_ROOT/README.txt"
hdiutil create \
  -volname "Moodtag ${VERSION}" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  "$DMG" >/dev/null

echo "Built: $PKG"
echo "Built: $DMG"
