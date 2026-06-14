"""Tests for bunshin.scheduler (cross-platform install/uninstall)."""
import platform
import shutil
import subprocess

import pytest

from bunshin.scheduler import (
    detect_platform,
    get_bunshin_binary,
    install_scheduler,
    scheduler_status,
    uninstall_scheduler,
)


def test_detect_platform_returns_known():
    plat = detect_platform()
    assert plat in {"macos", "linux-systemd", "linux-cron", "unknown"}


def test_detect_platform_matches_system():
    plat = detect_platform()
    sys = platform.system()
    if sys == "Darwin":
        assert plat == "macos"
    elif sys == "Linux":
        assert plat in {"linux-systemd", "linux-cron"}


def test_get_bunshin_binary_returns_path():
    """Even if not installed, returns a sensible path string."""
    p = get_bunshin_binary()
    assert isinstance(p, str)
    assert p.endswith("bunshin") or p.endswith("bunshin.exe")


def test_scheduler_status_shape():
    s = scheduler_status()
    assert "platform" in s
    assert "installed" in s
    assert isinstance(s["installed"], bool)


@pytest.mark.skipif(
    detect_platform() == "unknown",
    reason="Scheduler install/uninstall round-trip needs a supported platform",
)
def test_install_uninstall_roundtrip():
    """Install → status shows installed → uninstall → status shows not installed.

    NOTE: this is a real system mutation. On the developer's Mac it will
    overwrite the existing launchd plist (idempotent). We restore the
    previous state by re-running install at the end.
    """
    was_installed = scheduler_status().get("installed", False)
    try:
        ok, msg = install_scheduler()
        assert ok, msg
        assert scheduler_status().get("installed") is True

        ok, msg = uninstall_scheduler()
        assert ok, msg
        assert scheduler_status().get("installed") is False
    finally:
        # Restore previous state
        if was_installed:
            install_scheduler()
