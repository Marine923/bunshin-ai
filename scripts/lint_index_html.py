#!/usr/bin/env python3
"""Lint the JavaScript embedded in src/bunshin/web/server.py INDEX_HTML.

Catches the v0.9.20 class of bug — a `\\n` in a JS comment that Python
interpolated into a real newline, ending the `//` comment early and
feeding bare identifiers to the JS parser. SyntaxError → renderer
freezes → user reports "loading…" stuck forever.

How:
  1. Import the bunshin.web.server module so Python applies its normal
     triple-quoted string interpretation (which is what FastAPI ends up
     serving).
  2. Pull every <script>…</script> body out of INDEX_HTML.
  3. Concatenate and feed to `node --check`. Node ESM doesn't tolerate
     bare HTML around the script, so we strip tags first.

Exit 0 if syntax OK. Exit 1 if Node reports SyntaxError. Exit 2 if
something else went wrong (e.g. node not installed).

Designed to run before `pyinstaller` packages a build — wire it in via:

    uv run python scripts/lint_index_html.py && uv run pyinstaller …

so a broken build can't ship.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def _extract_scripts(html: str) -> list[tuple[int, str]]:
    """Return [(start_line, script_body), ...]."""
    out: list[tuple[int, str]] = []
    for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL):
        line = html[: m.start()].count("\n") + 1
        out.append((line, m.group(1)))
    return out


def _node_check(body: str) -> tuple[int, str]:
    """Run `node --check` on body; return (exit_code, stderr)."""
    node = shutil.which("node")
    if not node:
        print("[lint] WARNING: `node` not installed — skipping JS syntax check",
              file=sys.stderr)
        return 0, "node missing"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(body)
        path = f.name
    try:
        result = subprocess.run(
            [node, "--check", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stderr
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    try:
        from bunshin.web.server import INDEX_HTML
    except Exception as e:
        print(f"[lint] failed to import server.INDEX_HTML: {e}", file=sys.stderr)
        return 2

    scripts = _extract_scripts(INDEX_HTML)
    if not scripts:
        print("[lint] no <script> tags in INDEX_HTML — nothing to check")
        return 0

    total_lines = sum(s.count("\n") for _, s in scripts)
    print(f"[lint] checking {len(scripts)} <script> block(s), {total_lines:,} lines")

    # Join the bodies so node only parses once. Insert a sentinel line
    # comment between blocks so reported line numbers stay close to
    # the original layout.
    blob_parts: list[str] = []
    for start_line, body in scripts:
        blob_parts.append(f"//=== <script> at INDEX_HTML line {start_line} ===")
        blob_parts.append(body)
    blob = "\n".join(blob_parts)

    code, stderr = _node_check(blob)
    if code == 0:
        print("[lint] OK ✅  served JS parses cleanly")
        return 0

    print("[lint] ❌  Node syntax error in served JS:", file=sys.stderr)
    print(stderr, file=sys.stderr)
    print(
        "[lint] hint: if this looks like 'Unexpected identifier', a "
        "Python `\\n` in a JS // comment may have closed the comment early. "
        "Check the line range above against INDEX_HTML.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
