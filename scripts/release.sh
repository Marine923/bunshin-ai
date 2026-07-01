#!/usr/bin/env bash
# Release automation for Bunshin Memory.
#
# Usage:
#   scripts/release.sh <new-version> [--dry-run]
#
# What it does (in order):
#   1. Sanity: current dir is repo root, `main` branch clean, gh CLI available
#   2. Bumps version in pyproject.toml, electron-app/package.json, src/bunshin/__init__.py
#   3. Runs pytest → aborts on failure
#   4. Builds the desktop DMGs via scripts/build.sh
#   5. Installs the new build to /Applications for smoke-test
#   6. Verifies /api/health returns the new version
#   7. Commits (all bumped files + CHANGELOG if edited), tags, pushes
#   8. Creates GitHub release with both DMGs attached
#
# --dry-run stops after step 4 (builds but doesn't touch git or gh).
# You author the CHANGELOG entry beforehand; this script doesn't
# invent release notes.

set -euo pipefail

new_version="${1:-}"
dry_run=""
[[ "${2:-}" == "--dry-run" ]] && dry_run="1"

if [[ -z "$new_version" ]]; then
  echo "usage: $0 <new-version> [--dry-run]" >&2
  echo "  e.g.  $0 0.10.41" >&2
  exit 2
fi

if ! [[ "$new_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ version must be MAJOR.MINOR.PATCH (got: $new_version)" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

# ── 1. sanity
if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "❌ not on main branch" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]] && [[ -z "$dry_run" ]]; then
  echo "❌ working tree not clean. commit or stash first." >&2
  git status --short
  exit 1
fi
if ! command -v gh >/dev/null; then
  echo "❌ gh CLI missing (needed for release step)" >&2
  exit 1
fi

current_version="$(grep -m1 '^version = ' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')"
echo "current: $current_version"
echo "target:  $new_version"

# ── 2. bump version
sed -i.bak "s/^version = \"$current_version\"\$/version = \"$new_version\"/" pyproject.toml
sed -i.bak "s/\"version\": \"$current_version\"/\"version\": \"$new_version\"/" electron-app/package.json
sed -i.bak "s/__version__ = \"$current_version\"/__version__ = \"$new_version\"/" src/bunshin/__init__.py
rm -f pyproject.toml.bak electron-app/package.json.bak src/bunshin/__init__.py.bak

# ── 3. tests
echo "── running pytest ──"
uv run python -m pytest -q || { echo "❌ pytest failed — aborting"; exit 1; }

# ── 4. build
echo "── building DMGs ──"
bash scripts/build.sh

if [[ -n "$dry_run" ]]; then
  echo "✅ dry-run complete. DMGs in electron-app/dist/. Not touching git."
  exit 0
fi

# ── 5. install for smoke-test
echo "── installing to /Applications ──"
pkill -9 -f "Bunshin Memory" 2>/dev/null || true
sleep 2
rm -rf "/Applications/Bunshin Memory.app"
cp -R "electron-app/dist/mac-arm64/Bunshin Memory.app" /Applications/
xattr -dr com.apple.quarantine "/Applications/Bunshin Memory.app" 2>/dev/null || true
open -a "Bunshin Memory"
sleep 10

# ── 6. verify
health="$(curl -s http://127.0.0.1:8000/api/health || echo "")"
if [[ "$health" != *"\"version\":\"$new_version\""* ]]; then
  echo "❌ /api/health didn't report $new_version — got:"
  echo "  $health"
  exit 1
fi
echo "✅ health check passed: $health"

# ── 7. commit + tag + push
git add pyproject.toml electron-app/package.json src/bunshin/__init__.py
if ! git diff --cached --quiet CHANGELOG.md; then
  git add CHANGELOG.md
fi
git commit -m "Release v$new_version"
git tag "v$new_version"
git push origin main --tags

# ── 8. GitHub release
gh release create "v$new_version" \
  --title "v$new_version" \
  --notes "See CHANGELOG.md for details." \
  "./electron-app/dist/Bunshin Memory-$new_version-arm64.dmg" \
  "./electron-app/dist/Bunshin Memory-$new_version.dmg"

echo "✅ v$new_version released."
