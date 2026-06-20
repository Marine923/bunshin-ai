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


def restore_backup(db_path: Path, backup_path: Path) -> dict:
    """Restore the live DB from a backup snapshot.

    Safety: we copy the current DB aside first so a botched restore is
    recoverable.
    """
    import shutil
    import time
    out = {"ok": False, "restored_from": None, "previous_saved_to": None, "error": None}
    if not backup_path.exists() or not backup_path.is_file():
        out["error"] = f"backup not found: {backup_path}"
        return out
    try:
        if db_path.exists():
            stash = db_path.parent / f"{db_path.name}.pre-restore-{int(time.time())}"
            shutil.copy2(db_path, stash)
            out["previous_saved_to"] = str(stash)
        # Also stash the WAL / SHM files if present so the restored DB
        # doesn't accidentally see partial writes.
        for sidecar in ("-wal", "-shm"):
            sc = Path(str(db_path) + sidecar)
            if sc.exists():
                sc.unlink()
        shutil.copy2(backup_path, db_path)
        out["ok"] = True
        out["restored_from"] = str(backup_path)
    except Exception as e:
        out["error"] = str(e)
    return out


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
