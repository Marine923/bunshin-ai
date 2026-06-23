#!/usr/bin/env bash
# Convert a QuickTime screen recording to an optimized demo GIF for the README.
#
# Usage:
#   scripts/build-demo-gif.sh ~/Desktop/bunshin-demo.mov
#
# Output: docs/demo.gif (max 1200px wide, 12fps, < 8 MB target).
# Requires: ffmpeg (Homebrew: `brew install ffmpeg`). gifsicle is optional
# but recommended for an extra ~30% size cut (`brew install gifsicle`).

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <input.mov>" >&2
  exit 1
fi

INPUT="$1"
if [[ ! -f "$INPUT" ]]; then
  echo "input not found: $INPUT" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install with: brew install ffmpeg" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/docs"
OUT="$OUT_DIR/demo.gif"
PALETTE="$(mktemp -t bunshin-palette).png"
TMP_GIF="$(mktemp -t bunshin-demo).gif"

mkdir -p "$OUT_DIR"

# 1) Generate optimal palette for the clip (reduces banding dramatically).
ffmpeg -y -i "$INPUT" \
  -vf "fps=12,scale=1200:-1:flags=lanczos,palettegen=max_colors=128" \
  "$PALETTE"

# 2) Render the GIF using that palette.
ffmpeg -y -i "$INPUT" -i "$PALETTE" \
  -lavfi "fps=12,scale=1200:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=sierra2_4a" \
  "$TMP_GIF"

# 3) Optional second-pass optimization with gifsicle.
if command -v gifsicle >/dev/null 2>&1; then
  gifsicle -O3 --lossy=80 "$TMP_GIF" -o "$OUT"
else
  cp "$TMP_GIF" "$OUT"
  echo "Tip: install gifsicle (\`brew install gifsicle\`) for ~30% smaller GIFs." >&2
fi

rm -f "$PALETTE" "$TMP_GIF"

SIZE_BYTES=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT")
SIZE_MB=$(awk -v b="$SIZE_BYTES" 'BEGIN { printf "%.2f", b/1024/1024 }')
echo "wrote: $OUT (${SIZE_MB} MB)"
if (( SIZE_BYTES > 8000000 )); then
  echo "warning: GIF is over 8 MB — GitHub will accept it but it'll be slow to load." >&2
  echo "Consider trimming the .mov first or lowering fps in this script." >&2
fi
