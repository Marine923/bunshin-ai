"""Import browser history into bunshin memory.

Supports Safari and Chrome-family browsers on macOS. Reads the SQLite
history database via a COPY (because Chrome holds an exclusive lock
while running) and converts visit rows into bunshin records keyed by
URL.

Each record is `source='browser'` with metadata.browser indicating
which browser the visit came from. Re-importing is incremental: we
track the last imported visit timestamp in the settings table.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from bunshin.storage import insert_record


# Default history locations on macOS.
SAFARI_HISTORY = Path.home() / "Library" / "Safari" / "History.db"
CHROME_HISTORY = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "History"
ARC_HISTORY = Path.home() / "Library" / "Application Support" / "Arc" / "User Data" / "Default" / "History"

# Cocoa epoch starts at 2001-01-01 UTC; Safari stores visit_time as
# seconds since that epoch.
COCOA_EPOCH_OFFSET = 978307200

# Chrome stores visit_time as microseconds since 1601-01-01 UTC.
CHROME_EPOCH_OFFSET = 11644473600


def _safe_read_history(path: Path) -> Optional[Path]:
    """Copy the live history DB to a temp file so we can read it
    even if the browser is running (Chrome holds an exclusive lock)."""
    if not path.exists():
        return None
    tmp = Path(tempfile.gettempdir()) / f"bunshin-browser-{path.stem}-{int(datetime.now().timestamp())}.db"
    try:
        shutil.copy2(path, tmp)
        # SQLite often writes -wal and -shm sidecar files; copy them too.
        for ext in ("-wal", "-shm"):
            side = Path(str(path) + ext)
            if side.exists():
                shutil.copy2(side, Path(str(tmp) + ext))
        return tmp
    except (OSError, PermissionError):
        return None


def _read_safari(db_path: Path, since_ts: Optional[int]) -> Iterable[dict]:
    snap = _safe_read_history(db_path)
    if not snap:
        return
    conn = sqlite3.connect(snap)
    try:
        where = ""
        params: list = []
        if since_ts is not None:
            where = "WHERE v.visit_time + ? >= ?"
            params = [COCOA_EPOCH_OFFSET, since_ts]
        sql = f"""
            SELECT i.url, COALESCE(v.title, ''), v.visit_time + ?
            FROM history_items i
            JOIN history_visits v ON v.history_item = i.id
            {where}
            ORDER BY v.visit_time ASC
        """
        params = [COCOA_EPOCH_OFFSET] + params
        for row in conn.execute(sql, params):
            yield {
                "url": row[0],
                "title": row[1] or "",
                "timestamp": int(row[2]),
                "browser": "safari",
            }
    finally:
        conn.close()
        try:
            snap.unlink()
            for ext in ("-wal", "-shm"):
                side = Path(str(snap) + ext)
                if side.exists():
                    side.unlink()
        except OSError:
            pass


def _read_chromium(db_path: Path, since_ts: Optional[int], browser_label: str) -> Iterable[dict]:
    snap = _safe_read_history(db_path)
    if not snap:
        return
    conn = sqlite3.connect(snap)
    try:
        where = ""
        params: list = []
        if since_ts is not None:
            # Chromium stores microseconds since 1601-01-01.
            target_micros = (since_ts + CHROME_EPOCH_OFFSET) * 1_000_000
            where = "WHERE u.last_visit_time >= ?"
            params = [target_micros]
        sql = f"""
            SELECT u.url, u.title, u.last_visit_time
            FROM urls u
            {where}
            ORDER BY u.last_visit_time ASC
        """
        for row in conn.execute(sql, params):
            ts = int(row[2] / 1_000_000 - CHROME_EPOCH_OFFSET)
            yield {
                "url": row[0],
                "title": row[1] or "",
                "timestamp": ts,
                "browser": browser_label,
            }
    finally:
        conn.close()
        try:
            snap.unlink()
            for ext in ("-wal", "-shm"):
                side = Path(str(snap) + ext)
                if side.exists():
                    side.unlink()
        except OSError:
            pass


def _get_last_browser_ts(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?", ("browser_last_ts",)
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_browser_ts(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        ("browser_last_ts", str(ts)),
    )


def import_browser_history(
    conn: sqlite3.Connection,
    browsers: Optional[list[str]] = None,
    initial_days: int = 90,
    verbose: bool = False,
) -> dict:
    """Import recent browser visits.

    First run: covers the last `initial_days` days.
    Subsequent runs: incremental from the last seen timestamp.
    """
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {"safari": 0, "chrome": 0, "arc": 0, "skipped": 0, "errors": 0}

    last_ts = _get_last_browser_ts(conn)
    if last_ts is None:
        # First run — go back initial_days days.
        last_ts = int(datetime.now().timestamp()) - initial_days * 86400

    sources = browsers or ["safari", "chrome", "arc"]
    latest_seen = last_ts

    rows: list[dict] = []
    if "safari" in sources:
        for r in _read_safari(SAFARI_HISTORY, last_ts):
            rows.append(r)
            stats["safari"] += 1
    if "chrome" in sources:
        for r in _read_chromium(CHROME_HISTORY, last_ts, "chrome"):
            rows.append(r)
            stats["chrome"] += 1
    if "arc" in sources:
        for r in _read_chromium(ARC_HISTORY, last_ts, "arc"):
            rows.append(r)
            stats["arc"] += 1

    inserted = 0
    skipped = 0
    for row in rows:
        ts = row["timestamp"]
        if ts > latest_seen:
            latest_seen = ts
        title = row["title"].strip()
        url = row["url"].strip()
        if not url:
            continue
        # Skip noisy URLs (about:blank, chrome://, etc.)
        if url.startswith(("about:", "chrome://", "chrome-extension://", "javascript:")):
            skipped += 1
            continue
        # Compose searchable content. Include an ISO date so date-style
        # queries ("先週訪問した github") work via FTS5 + vector.
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).hostname or ""
        except Exception:
            domain = ""
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
        weekday = datetime.fromtimestamp(ts).strftime("%a") if ts else ""
        header_parts = [f"[{row['browser']}]"]
        if date_str:
            header_parts.append(date_str)
            header_parts.append(weekday)
        if domain:
            header_parts.append(domain)
        header = " ".join(header_parts)
        if title:
            content = f"{header}\n{title}\n{url}"
        else:
            content = f"{header}\n{url}"
        rid = insert_record(
            conn,
            source="browser",
            timestamp=ts,
            content=content,
            source_id=url,  # URL is the natural id
            metadata={
                "browser": row["browser"],
                "title": title[:300],
                "url": url[:1000],
                "domain": domain,
                "date": date_str,
            },
        )
        if rid:
            inserted += 1

    stats["skipped"] = skipped
    stats["inserted"] = inserted
    if rows:
        _set_last_browser_ts(conn, latest_seen)
        conn.commit()
    return stats
