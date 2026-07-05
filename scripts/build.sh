#!/usr/bin/env bash
# Run pre-build lint, then pyinstaller, then the Electron dmg pack.
# Fail fast if the JS embedded in INDEX_HTML doesn't parse — that's
# the v0.9.20 class of bug.
#
# v0.10.63 fail-fast hardening (post-mortem from v0.10.61):
#   - Clean ALL prior DMGs (including "Bunshin Memory-" prefix, not just
#     old "Bunshin-"), so a mid-build fail can't leave stale artifacts
#     that the install step silently picks up as if they were the new
#     version.
#   - After build, ASSERT that both arch DMGs for the current version
#     exist. If not, exit non-zero — no more silent partial success.
set -euo pipefail

cd "$(dirname "$0")/.."

# Read the current version from pyproject.toml so we can assert on it.
CURRENT_VERSION=$(grep -E '^version = "' pyproject.toml | head -1 | sed -E 's/^version = "(.+)"$/\1/')
if [[ -z "$CURRENT_VERSION" ]]; then
  echo "❌ Could not detect version from pyproject.toml" >&2
  exit 1
fi
echo "▶ Building version: $CURRENT_VERSION"

echo "▶ Cleaning ALL prior DMG artifacts (avoid stale-DMG install trap)..."
rm -rf electron-app/dist/mac-arm64 electron-app/dist/mac
# Both product-name prefixes: the old "Bunshin-" (pre-v0.10.27) and the
# current "Bunshin Memory-". Also blockmap sidecars.
rm -f electron-app/dist/Bunshin-*.dmg electron-app/dist/Bunshin-*.blockmap
rm -f "electron-app/dist/Bunshin Memory-"*.dmg "electron-app/dist/Bunshin Memory-"*.blockmap

echo "▶ Linting INDEX_HTML JavaScript..."
uv run python scripts/lint_index_html.py

echo "▶ pyinstaller..."
uv run pyinstaller bunshin.spec --clean -y

echo "▶ Electron dmg..."
cd electron-app
npm run dist:mac
cd ..

# Post-build assertion: the DMGs for the CURRENT version must exist.
INTEL_DMG="electron-app/dist/Bunshin Memory-${CURRENT_VERSION}.dmg"
ARM_DMG="electron-app/dist/Bunshin Memory-${CURRENT_VERSION}-arm64.dmg"
MISSING=()
[[ -f "$INTEL_DMG" ]] || MISSING+=("Intel: $INTEL_DMG")
[[ -f "$ARM_DMG" ]] || MISSING+=("arm64: $ARM_DMG")
if (( ${#MISSING[@]} > 0 )); then
  echo "❌ Build reported success but expected DMG(s) missing:" >&2
  for m in "${MISSING[@]}"; do echo "   - $m" >&2; done
  exit 2
fi

echo "✅ Build complete. DMGs verified for v$CURRENT_VERSION"
echo "   - $INTEL_DMG"
echo "   - $ARM_DMG"
