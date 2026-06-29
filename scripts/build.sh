#!/usr/bin/env bash
# Run pre-build lint, then pyinstaller, then the Electron dmg pack.
# Fail fast if the JS embedded in INDEX_HTML doesn't parse — that's
# the v0.9.20 class of bug.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "▶ Linting INDEX_HTML JavaScript..."
uv run python scripts/lint_index_html.py

echo "▶ pyinstaller..."
uv run pyinstaller bunshin.spec --clean -y

echo "▶ Electron dmg..."
cd electron-app
rm -rf dist/mac-arm64 dist/mac dist/Bunshin-*.dmg dist/Bunshin-*.blockmap
npm run dist:mac

echo "✅ Build complete. DMG(s) in electron-app/dist/"
