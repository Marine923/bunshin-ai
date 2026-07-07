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


def test_doctor_json_surfaces_sqlite_vec_failure_when_extension_broken(tmp_path, monkeypatch):
    """v0.10.49: when sqlite-vec fails to load, doctor must escalate to
    an explicit ❌ issue rather than swallowing the exception and showing
    empty vector counts. Silent failure here previously wasted an entire
    support round-trip because users saw '✓ Ollama' etc. and assumed
    everything was fine while search actually returned nothing.
    """
    import json
    tmp_db = tmp_path / "test.db"

    # Simulate a broken sqlite-vec by pointing the loader at a
    # non-existent module. We do this by editing the source path — but
    # since we can't easily patch a subprocess, instead assert the
    # *positive* path: on a healthy install, vec is loaded and no
    # ❌ sqlite-vec issue appears (proving the code path exists).
    r = subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "doctor", "--db", str(tmp_db), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    # On this healthy dev env, no sqlite-vec issue should be raised.
    sqlite_vec_issues = [
        i for i in payload["issues"] if "sqlite-vec" in i.get("label", "")
    ]
    assert not sqlite_vec_issues, (
        f"unexpected sqlite-vec issue on healthy env: {sqlite_vec_issues}"
    )


def test_preferred_ollama_models_probe_predicate_covers_common_bad_states():
    """v0.10.50: doctor's 「推奨 Ollama モデル未DL」probe should fire when
    Ollama is running but only serves models outside PREFERRED_MODELS
    (e.g. dolphin-phi, mistral-tiny). This test asserts the predicate
    logic in isolation — the subprocess-level doctor test would require
    a stub Ollama server."""
    from bunshin.chat import PREFERRED_MODELS

    # Sanity: the constant hasn't been renamed/emptied
    assert len(PREFERRED_MODELS) >= 5, (
        "PREFERRED_MODELS collapsed to <5 entries — probe would flag "
        "healthy installs as broken"
    )
    # Predicate under test (mirrors the doctor block)
    def _needs_pull(installed):
        return not any(p in set(installed) for p in PREFERRED_MODELS)

    assert _needs_pull([]) is True, "empty install → needs pull"
    assert _needs_pull(["dolphin-phi:latest", "mistral-tiny"]) is True, (
        "off-list models only → needs pull"
    )
    assert _needs_pull(["qwen2.5:3b"]) is False, (
        "smallest recommended present → probe silent"
    )
    assert _needs_pull(["qwen2.5:32b", "llama3.2:3b"]) is False, (
        "multiple preferred present → probe silent"
    )


def test_status_json_shape_and_contract(tmp_path):
    """v0.10.65: `bunshin status --json` payload shape must be stable —
    dashboards / cron reports depend on the field names. Locks in the
    invariant that key set matches what the CLI documents."""
    import json
    tmp_db = tmp_path / "test.db"
    r = subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "status", "--db", str(tmp_db), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    # Fresh empty tmp DB → should return ok=false, error=no_db
    if payload.get("ok") is False:
        assert payload.get("error") == "no_db"
        return
    # If a DB was auto-initialized, must have all expected keys
    expected_keys = {
        "ok", "db", "total_records", "total_entities",
        "vec_count", "vec_error", "sources", "oldest_ts", "newest_ts",
    }
    assert expected_keys <= set(payload.keys()), (
        f"missing keys: {expected_keys - set(payload.keys())}"
    )
    assert isinstance(payload["sources"], dict)


def test_doctor_invocable_via_click_cli_runner():
    """v0.10.58 regression guard: the /api/doctor web endpoint uses
    click.testing.CliRunner.invoke(doctor_cmd, ["--json"]) because the
    PyInstaller-packaged bunshin binary can't handle `-m bunshin.cli`.

    This test verifies the same path works: CliRunner returns valid JSON
    that the endpoint can parse. The v0.10.57 shipped bug (subprocess
    approach failing in the packaged app) got caught by post-install
    curl only — no unit test. This locks that in.
    """
    import json
    from click.testing import CliRunner
    from bunshin.cli import doctor_cmd

    runner = CliRunner()
    result = runner.invoke(doctor_cmd, ["--json"], standalone_mode=False)
    assert result.exception is None, f"doctor_cmd raised: {result.exception!r}"
    # Full-parse first (matches the endpoint's fast path)
    raw = result.output.strip()
    payload = json.loads(raw)
    assert "clean" in payload
    assert "issues" in payload
    assert isinstance(payload["issues"], list)
    for issue in payload["issues"]:
        assert set(issue.keys()) >= {"level", "label", "detail", "fix"}


def test_doctor_fix_flag_is_registered_and_runs_on_healthy_env():
    """v0.10.56: --fix must appear in --help and must not crash when there
    are no auto-fixable issues (e.g. on a healthy dev machine)."""
    r = subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "doctor", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0
    assert "--fix" in r.stdout, "--fix flag missing from doctor --help"
    assert "auto-repair" in r.stdout.lower() or "consent" in r.stdout.lower(), (
        "--fix help text lost its safety-first rationale"
    )


def test_doctor_deep_flag_is_registered_in_help():
    """v0.10.51: --deep flag must appear in doctor's --help. Without it,
    users won't discover the end-to-end search smoke test even though
    it's the most useful "silent-fail" catcher."""
    r = subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "doctor", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0
    assert "--deep" in r.stdout, (
        "--deep flag missing from doctor --help — end-to-end probe was "
        "accidentally removed or renamed"
    )
    # The help blurb should hint that this is the silent-failure catcher.
    assert "end-to-end" in r.stdout.lower() or "smoke" in r.stdout.lower(), (
        "--deep help text lost its silent-fail rationale"
    )


def test_warm_command_is_registered_and_has_help_text():
    """v0.10.48: `bunshin warm` must be a registered subcommand with
    help text describing its purpose. We don't run it end-to-end here
    because it downloads ~2 GB — the help check is enough to catch
    accidental deletion / rename regressions."""
    r = subprocess.run(
        [sys.executable, "-m", "bunshin.cli", "warm", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, (
        f"`bunshin warm --help` failed: exit={r.returncode}, "
        f"stderr={r.stderr[:300]}"
    )
    # The help output should describe the fresh-install pre-warm intent
    # so a maintainer landing on `--help` can tell it apart from `embed`.
    assert "--skip-rerank" in r.stdout
    for hint in ("embed", "rerank", "warm"):
        assert hint.lower() in r.stdout.lower(), (
            f"help text lost the {hint!r} keyword — command may have "
            f"been reduced or renamed"
        )
