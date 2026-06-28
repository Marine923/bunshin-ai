"""Import the user's Claude Code auto-memory notes into Bunshin storage.

Claude Code writes long-lived notes to:
  ~/.claude/projects/<project-slug>/memory/*.md

Each file is structured Markdown with YAML frontmatter (name, description,
metadata). They contain the user's own observations about projects, feedback
patterns, and references — exactly the kind of content Bunshin was built to
recall. v0.9.16-and-prior could not find them because no importer existed,
which Honda flagged as the contradiction "分身が自分が書いた memory を食え
ないのは矛盾".

Strategy
- One record per .md file (small enough — typical 200-2000 chars).
- Use the file's mtime as the record timestamp.
- source = "claude_memory" so it's distinguishable from chat transcripts.
- source_id = full path so we can dedup on re-import (delete + reinsert
  when mtime advances).
- metadata.{slug, project, frontmatter} for later filtering.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from bunshin.storage import insert_record


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def find_memory_files(claude_projects_dir: Path) -> Iterator[Path]:
    """Yield every *.md inside <claude_projects_dir>/*/memory/."""
    if not claude_projects_dir.exists():
        return
    for project_dir in claude_projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        mem_dir = project_dir / "memory"
        if not mem_dir.is_dir():
            continue
        for md in mem_dir.glob("*.md"):
            if md.is_file():
                yield md


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Both can be empty."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_block = m.group(1)
    body = text[m.end():]
    fm: dict = {}
    # Lightweight YAML — Claude only writes flat key:value + simple
    # nested `metadata:`. Don't pull in PyYAML for two fields.
    for line in fm_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("metadata:"):
            continue
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _read_memory_record(md_path: Path) -> Optional[dict]:
    """Build the storage record for one memory file. None on read failure."""
    try:
        text = md_path.read_text(encoding="utf-8")
        ts = int(md_path.stat().st_mtime)
    except OSError:
        return None
    fm, body = _parse_frontmatter(text)
    # The body is what's worth recalling. Frontmatter goes in metadata.
    content_parts = []
    if fm.get("description"):
        content_parts.append(fm["description"])
    if body.strip():
        content_parts.append(body.strip())
    content = "\n\n".join(content_parts).strip()
    if not content:
        return None
    # MEMORY.md is the index — skip its noise (one-line link list).
    if md_path.name == "MEMORY.md":
        return None
    return {
        "timestamp": ts,
        "content": content,
        "source_id": str(md_path),
        "metadata": {
            "slug": fm.get("name") or md_path.stem,
            "project": md_path.parent.parent.name,
            "frontmatter": fm,
        },
    }


def _get_last_mtime(conn: sqlite3.Connection, source_id: str) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"claude_memory_mtime:{source_id}",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_mtime(conn: sqlite3.Connection, source_id: str, mtime: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"claude_memory_mtime:{source_id}", str(mtime)),
    )


def _delete_existing(conn: sqlite3.Connection, source_id: str) -> None:
    cur = conn.execute(
        "SELECT id FROM records WHERE source = 'claude_memory' AND source_id = ?",
        (source_id,),
    )
    ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    try:
        conn.execute(f"DELETE FROM records_vec WHERE record_id IN ({placeholders})", ids)
    except sqlite3.OperationalError:
        pass
    conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", ids)


def import_claude_memory(
    conn: sqlite3.Connection,
    claude_projects_dir: Path,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """Import all Claude Code auto-memory notes. Reimports only changed files
    unless force=True."""
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "files_scanned": 0,
        "files_unchanged": 0,
        "files_reimported": 0,
        "files_skipped_empty": 0,
        "records_inserted": 0,
    }

    for md in find_memory_files(claude_projects_dir):
        stats["files_scanned"] += 1
        source_id = str(md)
        try:
            current_mtime = int(md.stat().st_mtime)
        except OSError:
            continue
        last_mtime = _get_last_mtime(conn, source_id)
        if not force and last_mtime is not None and last_mtime >= current_mtime:
            stats["files_unchanged"] += 1
            continue
        rec = _read_memory_record(md)
        if not rec:
            stats["files_skipped_empty"] += 1
            continue
        _delete_existing(conn, source_id)
        record_id = insert_record(
            conn,
            source="claude_memory",
            timestamp=rec["timestamp"],
            content=rec["content"],
            source_id=rec["source_id"],
            metadata=rec["metadata"],
        )
        if record_id:
            stats["records_inserted"] += 1
            stats["files_reimported"] += 1
        _set_last_mtime(conn, source_id, current_mtime)
        conn.commit()
        if verbose:
            print(f"Imported: {md} ({len(rec['content'])} chars)")
    return stats
