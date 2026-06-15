"""SQLite storage layer for Bunshin."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path.home() / ".bunshin" / "data.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    source_id       TEXT,
    timestamp       INTEGER NOT NULL,
    content         TEXT,
    content_hash    TEXT,
    metadata        TEXT,
    file_path       TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_timestamp ON records(timestamp);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(content_hash);

CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    config          TEXT NOT NULL,
    last_synced_at  INTEGER,
    enabled         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);
"""


def init_db(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_record(
    conn: sqlite3.Connection,
    source: str,
    timestamp: int,
    content: str,
    source_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    file_path: Optional[str] = None,
) -> Optional[str]:
    record_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    now = int(datetime.now(tz=timezone.utc).timestamp())

    cursor = conn.execute(
        "SELECT id FROM records WHERE content_hash = ? AND source = ?",
        (content_hash, source),
    )
    if cursor.fetchone():
        return None

    conn.execute(
        """INSERT INTO records
           (id, source, source_id, timestamp, content, content_hash, metadata, file_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record_id,
            source,
            source_id,
            timestamp,
            content,
            content_hash,
            json.dumps(metadata, ensure_ascii=False) if metadata else None,
            file_path,
            now,
            now,
        ),
    )
    conn.commit()
    return record_id


def count_records(conn: sqlite3.Connection, source: Optional[str] = None) -> int:
    if source:
        cursor = conn.execute("SELECT COUNT(*) FROM records WHERE source = ?", (source,))
    else:
        cursor = conn.execute("SELECT COUNT(*) FROM records")
    return cursor.fetchone()[0]


def list_sources_with_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    cursor = conn.execute(
        "SELECT source, COUNT(*) FROM records GROUP BY source ORDER BY COUNT(*) DESC"
    )
    return list(cursor.fetchall())


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into a connection."""
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def init_vector_db(conn: sqlite3.Connection, dimensions: int = 384) -> None:
    """Create the vector storage table (idempotent).

    If a table already exists with a different dimension, raises sqlite3.OperationalError
    on later inserts. Call drop_vector_db() first when migrating embedding models.
    """
    load_vec_extension(conn)
    conn.execute(
        f"""CREATE VIRTUAL TABLE IF NOT EXISTS records_vec USING vec0(
            record_id TEXT PRIMARY KEY,
            embedding FLOAT[{dimensions}]
        )"""
    )
    conn.commit()


def drop_vector_db(conn: sqlite3.Connection) -> None:
    """Drop the vector table — used when migrating to a different embedding model.

    Records themselves are preserved; only vectors are wiped and need re-embedding.
    """
    try:
        load_vec_extension(conn)
    except Exception:
        pass
    conn.execute("DROP TABLE IF EXISTS records_vec")
    conn.commit()


def detect_vec_dimensions(conn: sqlite3.Connection) -> Optional[int]:
    """Inspect the existing vec table to find its dimensions, or None if no table."""
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='records_vec'"
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        return None
    import re
    m = re.search(r"FLOAT\[(\d+)\]", row[0])
    return int(m.group(1)) if m else None


# ── FTS5 full-text search index ──

def init_fts(conn: sqlite3.Connection) -> None:
    """Create the FTS5 virtual table for keyword/BM25 search alongside vec search.

    Uses content='records' so it stays in sync via triggers we create below.
    Skips silently if FTS5 isn't compiled in (rare on macOS Python sqlite3).
    """
    try:
        conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                content,
                content='records',
                content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );

            CREATE TRIGGER IF NOT EXISTS records_ai_fts
                AFTER INSERT ON records BEGIN
                INSERT INTO records_fts(rowid, content) VALUES (new.rowid, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS records_ad_fts
                AFTER DELETE ON records BEGIN
                INSERT INTO records_fts(records_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS records_au_fts
                AFTER UPDATE ON records BEGIN
                INSERT INTO records_fts(records_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO records_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        # FTS5 not available, fall back silently
        pass


def fts_record_count(conn: sqlite3.Connection) -> int:
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM records_fts")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def rebuild_fts(conn: sqlite3.Connection) -> int:
    """Rebuild the FTS5 index from scratch — used after large back-fills."""
    try:
        conn.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
        conn.commit()
        return fts_record_count(conn)
    except sqlite3.OperationalError:
        return 0


def insert_vector(conn: sqlite3.Connection, record_id: str, embedding) -> None:
    """Store a vector for a record (caller batches commits)."""
    import numpy as np
    blob = np.asarray(embedding, dtype=np.float32).tobytes()
    conn.execute(
        "INSERT OR REPLACE INTO records_vec (record_id, embedding) VALUES (?, ?)",
        (record_id, blob),
    )


def count_vectors(conn: sqlite3.Connection) -> int:
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM records_vec")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def get_records_without_vectors(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return (id, content) for records that don't have an embedding yet."""
    cursor = conn.execute(
        """SELECT id, content FROM records
           WHERE content IS NOT NULL AND content != ''
             AND id NOT IN (SELECT record_id FROM records_vec)"""
    )
    return list(cursor.fetchall())


def count_short_records(conn: sqlite3.Connection, min_length: int = 20) -> int:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM records WHERE length(content) < ?",
        (min_length,),
    )
    return cursor.fetchone()[0]


def delete_short_records(conn: sqlite3.Connection, min_length: int = 20) -> int:
    """Delete records with content shorter than min_length. Returns count deleted."""
    cursor = conn.execute(
        "SELECT id FROM records WHERE length(content) < ?",
        (min_length,),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if not ids:
        return 0

    # Try to delete vectors first
    try:
        load_vec_extension(conn)
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            placeholders = ",".join(["?"] * len(batch))
            conn.execute(
                f"DELETE FROM records_vec WHERE record_id IN ({placeholders})",
                batch,
            )
    except sqlite3.OperationalError:
        pass

    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        placeholders = ",".join(["?"] * len(batch))
        conn.execute(
            f"DELETE FROM records WHERE id IN ({placeholders})",
            batch,
        )

    conn.commit()
    return len(ids)


def get_session_records(conn: sqlite3.Connection, source_id: str) -> list[dict]:
    """Get all records from a given session, ordered by timestamp."""
    cursor = conn.execute(
        """SELECT id, source, content, timestamp, metadata
           FROM records
           WHERE source_id = ?
           ORDER BY timestamp ASC, id ASC""",
        (source_id,),
    )
    results = []
    for row in cursor:
        metadata = json.loads(row[4]) if row[4] else None
        results.append(
            {
                "id": row[0],
                "source": row[1],
                "content": row[2],
                "timestamp": row[3],
                "metadata": metadata,
            }
        )
    return results
