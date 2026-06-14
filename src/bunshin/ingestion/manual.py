"""Manual memo insertion — capture anything you want to remember."""
import hashlib
import sqlite3
from datetime import datetime
from typing import Optional

from bunshin.storage import insert_record


def add_note(
    conn: sqlite3.Connection,
    content: str,
    tags: Optional[list[str]] = None,
    timestamp: Optional[int] = None,
) -> Optional[str]:
    """Insert a manual memo. Returns record_id on success, None if empty."""
    content = content.strip()
    if not content:
        return None

    ts = timestamp if timestamp is not None else int(datetime.now().timestamp())
    h = hashlib.sha256(f"{ts}:{content}".encode()).hexdigest()[:12]
    source_id = f"manual:{ts}:{h}"

    return insert_record(
        conn,
        source="manual",
        timestamp=ts,
        content=content,
        source_id=source_id,
        metadata={"tags": tags or [], "kind": "memo"},
    )
