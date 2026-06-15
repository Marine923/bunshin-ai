"""Backup the bunshin SQLite database to a versioned snapshot directory.

Strategy:
  - Use SQLite's online `VACUUM INTO` so the snapshot is consistent even
    while the DB is being written to.
  - Files land in ~/.bunshin/backups/data-YYYY-MM-DD.db
  - A retention policy keeps the most recent N daily files.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_BACKUP_DIR = Path.home() / ".bunshin" / "backups"


def backup_db(
    db_path: Path,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep: int = 7,
) -> dict:
    """Take a consistent snapshot of `db_path` into `backup_dir`.

    Returns a dict with: backup_path, bytes, retained, removed.
    """
    stats = {
        "backup_path": None,
        "bytes": 0,
        "retained": 0,
        "removed": 0,
        "error": None,
    }
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        stats["error"] = f"DB not found: {db_path}"
        return stats

    today = datetime.now().strftime("%Y-%m-%d")
    out = backup_dir / f"data-{today}.db"

    try:
        conn = sqlite3.connect(db_path)
        try:
            # VACUUM INTO writes a fresh, compact copy. Removes any free pages.
            conn.execute(f"VACUUM INTO '{out}'")
        finally:
            conn.close()
        stats["backup_path"] = str(out)
        stats["bytes"] = out.stat().st_size
    except sqlite3.OperationalError as e:
        stats["error"] = f"vacuum failed: {e}"
        return stats

    # Retention: keep the `keep` most-recently-modified backups.
    existing = sorted(
        backup_dir.glob("data-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keepers = existing[:keep]
    to_remove = existing[keep:]
    for f in to_remove:
        try:
            f.unlink()
            stats["removed"] += 1
        except OSError:
            pass
    stats["retained"] = len(keepers)
    return stats


def list_backups(backup_dir: Path = DEFAULT_BACKUP_DIR) -> list[dict]:
    if not backup_dir.exists():
        return []
    out = []
    for p in sorted(backup_dir.glob("data-*.db"), reverse=True):
        try:
            st = p.stat()
            out.append({
                "path": str(p),
                "name": p.name,
                "bytes": st.st_size,
                "mtime": int(st.st_mtime),
                "mtime_str": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except OSError:
            continue
    return out
