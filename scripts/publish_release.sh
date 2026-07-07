#!/usr/bin/env bash
# Publish a Bunshin release to GitHub with both arch DMGs.
#
# Usage:
#   scripts/publish_release.sh v0.10.67 "release title" "release-notes.md"
#
# What it does (fail-fast at every step):
#   1. Read $CURRENT_VERSION from pyproject.toml, cross-check with argv tag.
#   2. Assert both DMGs exist in electron-app/dist/ for that version.
#   3. Create the release as a DRAFT (idempotent — if the tag already has
#      a release, use it).
#   4. Upload BOTH DMGs with --clobber so re-runs are safe.
#   5. Verify the release now has both assets.
#   6. Flip draft → false (publish).
#   7. Print the release URL.
#
# History: v0.10.57 and v0.10.66 shipped with 0 assets or wrong assets
# because the ad-hoc `gh release create ... && gh release upload ...`
# commands failed silently in the middle (timeouts, HTTP 400 on second
# upload). Wrapping them here makes the whole flow one exit-code.
set -euo pipefail

TAG="${1:-}"
TITLE="${2:-}"
NOTES_FILE="${3:-}"

if [[ -z "$TAG" ]] || [[ -z "$TITLE" ]] || [[ -z "$NOTES_FILE" ]]; then
  echo "usage: $0 <tag> <title> <notes-file>" >&2
  echo "  <tag>: e.g. v0.10.67 (must start with v)" >&2
  echo "  <title>: release title" >&2
  echo "  <notes-file>: path to a file with release notes" >&2
  exit 1
fi

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ tag must look like v0.10.67, got: $TAG" >&2
  exit 1
fi

if [[ ! -f "$NOTES_FILE" ]]; then
  echo "❌ notes file not found: $NOTES_FILE" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

# Cross-check tag against pyproject.toml.
VERSION="${TAG#v}"
PYPROJ_VERSION=$(grep -E '^version = "' pyproject.toml | head -1 | sed -E 's/^version = "(.+)"$/\1/')
if [[ "$PYPROJ_VERSION" != "$VERSION" ]]; then
  echo "❌ tag $TAG expects version $VERSION but pyproject.toml says $PYPROJ_VERSION" >&2
  exit 1
fi

INTEL_DMG="electron-app/dist/Bunshin Memory-${VERSION}.dmg"
ARM_DMG="electron-app/dist/Bunshin Memory-${VERSION}-arm64.dmg"
if [[ ! -f "$INTEL_DMG" ]]; then
  echo "❌ Intel DMG missing: $INTEL_DMG" >&2
  echo "   Run: bash scripts/build.sh" >&2
  exit 1
fi
if [[ ! -f "$ARM_DMG" ]]; then
  echo "❌ arm64 DMG missing: $ARM_DMG" >&2
  echo "   Run: bash scripts/build.sh" >&2
  exit 1
fi

echo "▶ Version cross-checked: $VERSION"
echo "▶ Intel DMG: $INTEL_DMG"
echo "▶ arm64 DMG: $ARM_DMG"

# Phase 1: create draft release (idempotent).
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "▶ Release $TAG already exists — re-using it (idempotent)"
else
  echo "▶ Creating draft release $TAG..."
  gh release create "$TAG" --draft --title "$TITLE" --notes-file "$NOTES_FILE"
fi

# Phase 2: upload both DMGs (--clobber makes re-runs safe).
echo "▶ Uploading Intel DMG..."
gh release upload "$TAG" "$INTEL_DMG" --clobber
echo "▶ Uploading arm64 DMG..."
gh release upload "$TAG" "$ARM_DMG" --clobber

# Phase 3: verify both assets exist.
echo "▶ Verifying assets..."
ASSETS=$(gh release view "$TAG" --json assets --jq '[.assets[].name] | join(",")')
MISSING=()
[[ "$ASSETS" == *"$(basename "$INTEL_DMG" | tr ' ' '.')"* ]] || MISSING+=("Intel")
[[ "$ASSETS" == *"$(basename "$ARM_DMG" | tr ' ' '.')"* ]] || MISSING+=("arm64")
if (( ${#MISSING[@]} > 0 )); then
  echo "❌ Release $TAG missing assets after upload: ${MISSING[*]}" >&2
  echo "   Current assets: $ASSETS" >&2
  exit 2
fi

# Phase 4: publish (draft → false).
echo "▶ Publishing (draft → false)..."
gh release edit "$TAG" --draft=false

URL=$(gh release view "$TAG" --json url --jq .url)
echo "✅ Published: $URL"
echo "   Assets: $ASSETS"
