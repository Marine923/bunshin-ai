"""Import Apple Notes via AppleScript.

Uses osascript to fetch all notes from Notes.app — no sandbox issues, no
Full Disk Access required. Each note's HTML body is converted to plain
text and stored as a bunshin record keyed by the note's CoreData id.

Incremental imports: per-note modification timestamps are tracked in
the settings table so subsequent runs only re-import changed notes.
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional

from bunshin.storage import insert_record


# AppleScript that emits notes as a delimited stream. We use distinctive
# delimiters (rather than CSV/JSON) because note bodies contain anything.
_NOTES_APPLESCRIPT = r'''
set fieldDelim to "<<<BUNSHIN_FIELD>>>"
set noteDelim to "<<<BUNSHIN_NOTE_END>>>"
set output to ""
tell application "Notes"
    set allNotes to every note
    repeat with theNote in allNotes
        try
            set noteId to id of theNote as string
            set noteName to name of theNote as string
            set noteBody to body of theNote as string
            set noteMod to (modification date of theNote) as string
            set noteCreated to (creation date of theNote) as string
            try
                set folderName to (name of container of theNote) as string
            on error
                set folderName to ""
            end try
            set output to output & noteId & fieldDelim & noteName & fieldDelim & noteMod & fieldDelim & noteCreated & fieldDelim & folderName & fieldDelim & noteBody & noteDelim
        end try
    end repeat
end tell
return output
'''


def _run_applescript(script: str, timeout: int = 600) -> Optional[str]:
    """Run an AppleScript and return its stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


class _HTMLToText(HTMLParser):
    """Convert Notes' HTML body to plain text with reasonable structure."""

    BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}
    SKIP_TAGS = {"script", "style"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def html_to_text(html: str) -> str:
    """Strip HTML tags from a Notes body, preserving block structure."""
    parser = _HTMLToText()
    try:
        parser.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", "", html).strip()
    text = parser.get_text()
    # Collapse excessive whitespace
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _parse_applescript_date(s: str) -> Optional[int]:
    """Parse AppleScript's locale-dependent date string into a Unix timestamp.

    macOS English locale:
        "Monday, June 16, 2026 at 10:30:00 AM"
    macOS Japanese locale:
        "2026年6月16日月曜日 10:30:00"
    """
    s = s.strip()
    if not s:
        return None

    formats = [
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%A, %B %d, %Y at %H:%M:%S",
        "%a %b %d %H:%M:%S %Y",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except ValueError:
            continue

    # Japanese: "2026年6月16日月曜日 10:30:00" OR "2026年6月15日 月曜日 15:47:28"
    # The weekday is optional; AppleScript adds a space before it on macOS
    # 12+ (Monterey) but not earlier.
    m = re.match(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*\S*\s+(\d{1,2}):(\d{2}):(\d{2})",
        s,
    )
    if m:
        try:
            y, mo, d, h, mi, se = (int(x) for x in m.groups())
            return int(datetime(y, mo, d, h, mi, se).timestamp())
        except ValueError:
            pass
    return None


def parse_notes_output(raw: str) -> list[dict]:
    """Parse the delimited AppleScript output into note dicts."""
    notes = []
    for block in raw.split("<<<BUNSHIN_NOTE_END>>>"):
        block = block.strip()
        if not block:
            continue
        parts = block.split("<<<BUNSHIN_FIELD>>>")
        if len(parts) < 6:
            continue
        note_id, name, mod_str, created_str, folder = (p.strip() for p in parts[:5])
        body = parts[5]  # preserve internal whitespace of the body
        notes.append({
            "id": note_id,
            "name": name,
            "folder": folder,
            "modified": _parse_applescript_date(mod_str),
            "created": _parse_applescript_date(created_str),
            "body_html": body,
        })
    return notes


def _get_last_seen(conn: sqlite3.Connection, note_id: str) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"notes_mod:{note_id}",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_seen(conn: sqlite3.Connection, note_id: str, ts: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"notes_mod:{note_id}", str(ts)),
    )


def _delete_existing(conn: sqlite3.Connection, source_id: str) -> None:
    cur = conn.execute(
        "SELECT id FROM records WHERE source = 'notes' AND source_id = ?",
        (source_id,),
    )
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    try:
        conn.execute(
            f"DELETE FROM records_vec WHERE record_id IN ({placeholders})",
            ids,
        )
    except sqlite3.OperationalError:
        pass
    conn.execute(
        f"DELETE FROM records WHERE id IN ({placeholders})",
        ids,
    )


def import_apple_notes(
    conn: sqlite3.Connection,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """Import all Apple Notes via AppleScript.

    Returns: scanned, unchanged, imported, failed, chunks, applescript_failed.
    """
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "scanned": 0,
        "unchanged": 0,
        "imported": 0,
        "failed": 0,
        "chunks": 0,
        "applescript_failed": False,
    }

    raw = _run_applescript(_NOTES_APPLESCRIPT)
    if raw is None:
        stats["applescript_failed"] = True
        return stats

    notes = parse_notes_output(raw)
    from bunshin.ingestion.files import chunk_text

    for note in notes:
        stats["scanned"] += 1
        note_id = note["id"] or note["name"] or ""
        if not note_id:
            stats["failed"] += 1
            continue
        mod_ts = note["modified"] or int(datetime.now().timestamp())

        last_seen = _get_last_seen(conn, note_id)
        if not force and last_seen is not None and last_seen >= mod_ts:
            stats["unchanged"] += 1
            continue

        text = html_to_text(note["body_html"])
        if not text and not note["name"]:
            stats["failed"] += 1
            continue

        # Re-import: wipe old chunks for this note
        _delete_existing(conn, note_id)

        header_parts = ["[notes]"]
        date_str = (
            datetime.fromtimestamp(mod_ts).strftime("%Y-%m-%d")
            if mod_ts else ""
        )
        if date_str:
            header_parts.append(date_str)
        if note["folder"]:
            header_parts.append(note["folder"])
        header = " ".join(header_parts)

        title = note["name"] or "(無題)"
        full_text = f"{header}\n{title}\n\n{text}".strip()
        chunks = chunk_text(full_text) or [full_text]

        for i, chunk in enumerate(chunks):
            insert_record(
                conn,
                source="notes",
                timestamp=mod_ts,
                content=chunk,
                source_id=note_id,
                metadata={
                    "title": title,
                    "folder": note["folder"],
                    "created": note["created"],
                    "modified": mod_ts,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                },
            )
            stats["chunks"] += 1

        _set_last_seen(conn, note_id, mod_ts)
        conn.commit()
        stats["imported"] += 1
        if verbose:
            print(f"Imported: {title} ({len(chunks)} chunks)")

    return stats
