"""Regression tests for v0.10.40 `bunshin doctor --json` mode.

The JSON output shape is a public contract — CI / cron / other
scripts parse it. Any drift (missing key, changed level, altered
field name) silently breaks downstream consumers.
"""
import json
import subprocess
import sys


def _run_doctor(args):
    """Invoke the doctor CLI in a subprocess (real click entry point)."""
    return subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "doctor", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_doctor_json_output_is_valid_json_with_expected_shape(tmp_path):
    """The --json output must be raw JSON on stdout with keys
    `clean` (bool) and `issues` (array of {level, label, detail, fix})."""
    tmp_db = tmp_path / "test.db"
    r = _run_doctor(["--db", str(tmp_db), "--json"])
    assert r.returncode == 0, (
        f"exit={r.returncode}; stderr:\n{r.stderr[:500]}"
    )
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"stdout is not valid JSON: {e}\n---stdout---\n{r.stdout[:500]}"
        )
    assert "clean" in payload, "missing top-level `clean` key"
    assert "issues" in payload, "missing top-level `issues` key"
    assert isinstance(payload["clean"], bool)
    assert isinstance(payload["issues"], list)
    for issue in payload["issues"]:
        assert set(issue.keys()) >= {"level", "label", "detail", "fix"}, (
            f"issue missing required keys: {issue}"
        )


def test_doctor_json_clean_flag_matches_issue_presence(tmp_path):
    tmp_db = tmp_path / "test.db"
    r = _run_doctor(["--db", str(tmp_db), "--json"])
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    if payload["issues"]:
        assert payload["clean"] is False
    else:
        assert payload["clean"] is True


def test_doctor_json_stdout_has_no_rich_escape_codes(tmp_path):
    """--json must not leak ANSI colour codes or Rich box characters
    into stdout — downstream parsers will choke on them."""
    tmp_db = tmp_path / "test.db"
    r = _run_doctor(["--db", str(tmp_db), "--json"])
    assert r.returncode == 0
    assert "\x1b[" not in r.stdout, "ANSI escape leaked into --json stdout"
    for banner_marker in ("🩺", "── 改善できる項目 ──", "🎉"):
        assert banner_marker not in r.stdout, (
            f"human-mode banner {banner_marker!r} leaked into --json output"
        )


def test_doctor_default_mode_prints_human_banner(tmp_path):
    tmp_db = tmp_path / "test.db"
    r = _run_doctor(["--db", str(tmp_db)])
    assert r.returncode == 0
    assert "🩺" in r.stdout, "human-mode banner missing"


def test_doctor_default_mode_surfaces_v0_10_47_probes(tmp_path):
    """v0.10.47 β-tester diagnostics: doctor must probe the four items
    that cause the most first-run confusion (silent embed download, silent
    rerank download, disk-full silent failure, and runtime info needed
    for bug reports). Each item can be a green ✓ or an issue — we just
    verify the probe ran and emitted a labelled line."""
    tmp_db = tmp_path / "test.db"
    r = _run_doctor(["--db", str(tmp_db)])
    assert r.returncode == 0
    out = r.stdout
    # Runtime line always prints (Python version, OS, arch) as a dim footer.
    assert "Python" in out, (
        "runtime version footer missing — β testers need this in bug reports"
    )
    # Each of the four probes must at least mention its topic word.
    # "Embedding" / "Reranker" appear as either ✓ line or ⚠/ℹ issue label.
    for topic in ("Embedding", "Reranker", "ディスク"):
        assert topic in out, (
            f"doctor never mentioned {topic!r} — probe removed or crashed silently"
        )
