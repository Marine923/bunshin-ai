"""Cross-platform scheduler for `bunshin update`.

Installs a recurring (hourly) update task using the right OS mechanism:
  - macOS              → launchd user agent
  - Linux + systemd    → systemd --user timer + service
  - Linux + cron only  → crontab entry

All three converge on running `~/.bunshin/venv/bin/bunshin update --quiet`
every hour and appending output to ~/.bunshin/logs/update.{out,err}.log.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Tuple


# ────────────────────────────────────────────────────────────
# Common helpers
# ────────────────────────────────────────────────────────────

def get_bunshin_binary() -> str:
    """Find the bunshin CLI binary path."""
    candidates = [
        Path.home() / ".bunshin" / "venv" / "bin" / "bunshin",
        Path("/usr/local/bin/bunshin"),
        Path("/opt/homebrew/bin/bunshin"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(Path.home() / ".bunshin" / "venv" / "bin" / "bunshin")


def ensure_logs_dir() -> Path:
    p = Path.home() / ".bunshin" / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def detect_platform() -> str:
    """Return 'macos', 'linux-systemd', 'linux-cron', or 'unknown'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        # Prefer systemd user mode if available
        try:
            r = subprocess.run(
                ["systemctl", "--user", "show-environment"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return "linux-systemd"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Fallback to crontab
        try:
            r = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=5
            )
            if r.returncode in (0, 1):  # 1 = no crontab yet, still ok
                return "linux-cron"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return "unknown"


# ────────────────────────────────────────────────────────────
# macOS launchd
# ────────────────────────────────────────────────────────────

LAUNCHD_LABEL = "com.bunshin.update"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def install_launchd(interval_seconds: int = 3600) -> Tuple[bool, str]:
    bin_path = get_bunshin_binary()
    logs = ensure_logs_dir()
    home = str(Path.home())

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bin_path}</string>
        <string>update</string>
        <string>--quiet</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{logs}/update.out.log</string>
    <key>StandardErrorPath</key>
    <string>{logs}/update.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{home}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""
    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHD_PLIST.write_text(plist)

    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
    r = subprocess.run(
        ["launchctl", "load", str(LAUNCHD_PLIST)], capture_output=True, text=True
    )
    if r.returncode != 0:
        return False, f"launchctl load failed: {r.stderr.strip()}"
    return True, f"Installed launchd job (every {interval_seconds}s) at {LAUNCHD_PLIST}"


def uninstall_launchd() -> Tuple[bool, str]:
    if not LAUNCHD_PLIST.exists():
        return True, "launchd job not installed (nothing to remove)"
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)
    LAUNCHD_PLIST.unlink()
    return True, f"Removed launchd job ({LAUNCHD_PLIST})"


def status_launchd() -> dict:
    out = {"installed": LAUNCHD_PLIST.exists(), "active": False, "path": str(LAUNCHD_PLIST)}
    if out["installed"]:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        out["active"] = LAUNCHD_LABEL in (r.stdout or "")
    return out


# ────────────────────────────────────────────────────────────
# Linux systemd (--user)
# ────────────────────────────────────────────────────────────

SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_SERVICE = "bunshin-update.service"
SYSTEMD_TIMER = "bunshin-update.timer"


def install_systemd(interval: str = "1h") -> Tuple[bool, str]:
    bin_path = get_bunshin_binary()
    ensure_logs_dir()
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)

    service = f"""[Unit]
Description=Bunshin incremental update

[Service]
Type=oneshot
ExecStart={bin_path} update --quiet
StandardOutput=append:%h/.bunshin/logs/update.out.log
StandardError=append:%h/.bunshin/logs/update.err.log
"""
    timer = f"""[Unit]
Description=Run bunshin update every {interval}

[Timer]
OnBootSec=10min
OnUnitActiveSec={interval}
Unit={SYSTEMD_SERVICE}

[Install]
WantedBy=timers.target
"""
    (SYSTEMD_DIR / SYSTEMD_SERVICE).write_text(service)
    (SYSTEMD_DIR / SYSTEMD_TIMER).write_text(timer)

    for cmd in [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", SYSTEMD_TIMER],
        ["systemctl", "--user", "start", SYSTEMD_TIMER],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"{' '.join(cmd)} failed: {r.stderr.strip()}"
    return True, f"Installed systemd --user timer (every {interval}) at {SYSTEMD_DIR}/"


def uninstall_systemd() -> Tuple[bool, str]:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", SYSTEMD_TIMER],
        capture_output=True,
    )
    removed = False
    for f in (SYSTEMD_TIMER, SYSTEMD_SERVICE):
        p = SYSTEMD_DIR / f
        if p.exists():
            p.unlink()
            removed = True
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return True, "Removed systemd unit files" if removed else "systemd timer not installed"


def status_systemd() -> dict:
    timer = SYSTEMD_DIR / SYSTEMD_TIMER
    out = {"installed": timer.exists(), "active": False, "path": str(SYSTEMD_DIR)}
    if out["installed"]:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", SYSTEMD_TIMER],
            capture_output=True, text=True,
        )
        out["active"] = r.stdout.strip() == "active"
    return out


# ────────────────────────────────────────────────────────────
# Linux cron fallback
# ────────────────────────────────────────────────────────────

CRON_MARKER = "# bunshin-update"


def _current_crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(content: str) -> Tuple[bool, str]:
    p = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    if p.returncode != 0:
        return False, p.stderr.strip()
    return True, ""


def install_cron() -> Tuple[bool, str]:
    bin_path = get_bunshin_binary()
    ensure_logs_dir()
    cron_line = (
        f"0 * * * * {bin_path} update --quiet "
        f">> $HOME/.bunshin/logs/update.out.log "
        f"2>> $HOME/.bunshin/logs/update.err.log {CRON_MARKER}"
    )
    existing = _current_crontab()
    lines = [l for l in existing.splitlines() if CRON_MARKER not in l]
    lines.append(cron_line)
    new = "\n".join(lines).rstrip() + "\n"
    ok, err = _write_crontab(new)
    if not ok:
        return False, f"crontab write failed: {err}"
    return True, "Installed cron entry (hourly)"


def uninstall_cron() -> Tuple[bool, str]:
    existing = _current_crontab()
    if CRON_MARKER not in existing:
        return True, "cron entry not present"
    lines = [l for l in existing.splitlines() if CRON_MARKER not in l]
    new = "\n".join(lines).rstrip() + "\n"
    ok, err = _write_crontab(new)
    if not ok:
        return False, f"crontab update failed: {err}"
    return True, "Removed cron entry"


def status_cron() -> dict:
    crontab = _current_crontab()
    return {
        "installed": CRON_MARKER in crontab,
        "active": CRON_MARKER in crontab,
        "path": "crontab",
    }


# ────────────────────────────────────────────────────────────
# Unified API
# ────────────────────────────────────────────────────────────

def install_scheduler() -> Tuple[bool, str]:
    plat = detect_platform()
    if plat == "macos":
        return install_launchd()
    if plat == "linux-systemd":
        return install_systemd()
    if plat == "linux-cron":
        return install_cron()
    return False, f"Unsupported platform ({platform.system()})"


def uninstall_scheduler() -> Tuple[bool, str]:
    plat = detect_platform()
    if plat == "macos":
        return uninstall_launchd()
    if plat == "linux-systemd":
        return uninstall_systemd()
    if plat == "linux-cron":
        return uninstall_cron()
    return False, f"Unsupported platform ({platform.system()})"


def scheduler_status() -> dict:
    plat = detect_platform()
    out: dict = {"platform": plat}
    if plat == "macos":
        out.update(status_launchd())
    elif plat == "linux-systemd":
        out.update(status_systemd())
    elif plat == "linux-cron":
        out.update(status_cron())
    else:
        out.update({"installed": False, "active": False, "path": None})
    return out
