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
    _migrate_signals(conn)
    conn.commit()
    return conn


def _migrate_signals(conn: sqlite3.Connection) -> None:
    """Idempotent migration: add signal/learning columns + the rules table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(records)").fetchall()}
    if 'signal_score' not in cols:
        conn.execute("ALTER TABLE records ADD COLUMN signal_score REAL")
    if 'user_signal' not in cols:
        # 0 = untouched, 1 = user said "hide", 2 = user said "important"
        conn.execute("ALTER TABLE records ADD COLUMN user_signal INTEGER DEFAULT 0")
    if 'sender' not in cols:
        conn.execute("ALTER TABLE records ADD COLUMN sender TEXT")
    if 'sender_domain' not in cols:
        conn.execute("ALTER TABLE records ADD COLUMN sender_domain TEXT")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type       TEXT NOT NULL,
            pattern         TEXT NOT NULL,
            action          TEXT NOT NULL,
            source_filter   TEXT,
            applied_count   INTEGER DEFAULT 0,
            created_at      INTEGER NOT NULL
        )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_rules_unique "
        "ON learning_rules(rule_type, pattern, action)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_signal_score ON records(signal_score DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_user_signal ON records(user_signal)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_sender ON records(sender)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_sender_domain ON records(sender_domain)")


def recompute_signals(conn: sqlite3.Connection, only_missing: bool = False) -> int:
    """Re-score every record's signal_score and cache sender / domain.

    Used at startup (with only_missing=True, fast) and from the CLI
    `bunshin recompute-signals` (with only_missing=False, slower).
    """
    from bunshin.signals import compute_signal_score, extract_sender
    if only_missing:
        rows = conn.execute(
            "SELECT id, source, metadata, content FROM records WHERE signal_score IS NULL"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, source, metadata, content FROM records"
        ).fetchall()
    updated = 0
    for rid, source, metadata, content in rows:
        sender, domain = extract_sender(metadata)
        score = compute_signal_score(content or "", source, sender, domain)
        conn.execute(
            "UPDATE records SET signal_score = ?, sender = ?, sender_domain = ? WHERE id = ?",
            (score, sender, domain, rid),
        )
        updated += 1
        if updated % 500 == 0:
            conn.commit()
    conn.commit()
    return updated


# ---- Learning-rule helpers (called by the FastAPI endpoints) -----------

def apply_mark(
    conn: sqlite3.Connection,
    record_id: str,
    action: str,
    scope: str,
) -> dict:
    """Mark a record (and optionally a sender/domain) as hide or important.

    action: 'hide' or 'star'
    scope:  'record' | 'sender' | 'domain'
    Returns {applied, rule_id, sender, domain}.
    """
    import time
    row = conn.execute(
        "SELECT sender, sender_domain, source FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    if not row:
        return {"applied": 0, "error": "record not found"}
    sender, domain, source = row
    target = 1 if action == "hide" else 2
    rule_id = None
    applied = 0
    if scope == "record":
        cur = conn.execute(
            "UPDATE records SET user_signal = ? WHERE id = ?", (target, record_id)
        )
        applied = cur.rowcount
    elif scope == "sender" and sender:
        cur = conn.execute(
            "UPDATE records SET user_signal = ? WHERE sender = ? AND user_signal = 0",
            (target, sender),
        )
        applied = cur.rowcount or 0
        # Always record at least the source record's flip.
        conn.execute(
            "UPDATE records SET user_signal = ? WHERE id = ?", (target, record_id)
        )
        if applied == 0:
            applied = 1
        conn.execute(
            """INSERT INTO learning_rules
                 (rule_type, pattern, action, source_filter, applied_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(rule_type, pattern, action)
               DO UPDATE SET applied_count = applied_count + excluded.applied_count""",
            ("sender", sender, action, None, applied, int(time.time())),
        )
        rule_id = conn.execute(
            "SELECT id FROM learning_rules WHERE rule_type=? AND pattern=? AND action=?",
            ("sender", sender, action),
        ).fetchone()[0]
    elif scope == "domain" and domain:
        cur = conn.execute(
            "UPDATE records SET user_signal = ? WHERE sender_domain = ? AND user_signal = 0",
            (target, domain),
        )
        applied = cur.rowcount or 0
        conn.execute(
            "UPDATE records SET user_signal = ? WHERE id = ?", (target, record_id)
        )
        if applied == 0:
            applied = 1
        conn.execute(
            """INSERT INTO learning_rules
                 (rule_type, pattern, action, source_filter, applied_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(rule_type, pattern, action)
               DO UPDATE SET applied_count = applied_count + excluded.applied_count""",
            ("domain", domain, action, None, applied, int(time.time())),
        )
        rule_id = conn.execute(
            "SELECT id FROM learning_rules WHERE rule_type=? AND pattern=? AND action=?",
            ("domain", domain, action),
        ).fetchone()[0]
    else:
        # Sender/domain scope but record has no parseable sender — fall back.
        conn.execute(
            "UPDATE records SET user_signal = ? WHERE id = ?", (target, record_id)
        )
        applied = 1
        scope = "record"
    conn.commit()
    return {
        "applied": applied,
        "scope": scope,
        "rule_id": rule_id,
        "sender": sender,
        "domain": domain,
    }


def undo_rule(conn: sqlite3.Connection, rule_id: int) -> dict:
    """Reverse a learning rule: flip its records back to user_signal=0 and delete."""
    row = conn.execute(
        "SELECT rule_type, pattern, action FROM learning_rules WHERE id = ?", (rule_id,)
    ).fetchone()
    if not row:
        return {"ok": False, "error": "rule not found"}
    rule_type, pattern, action = row
    target = 1 if action == "hide" else 2
    col = "sender" if rule_type == "sender" else "sender_domain"
    cur = conn.execute(
        f"UPDATE records SET user_signal = 0 WHERE user_signal = ? AND {col} = ?",
        (target, pattern),
    )
    reverted = cur.rowcount or 0
    conn.execute("DELETE FROM learning_rules WHERE id = ?", (rule_id,))
    conn.commit()
    return {"ok": True, "reverted": reverted, "pattern": pattern}


def undo_record_mark(conn: sqlite3.Connection, record_id: str) -> dict:
    conn.execute("UPDATE records SET user_signal = 0 WHERE id = ?", (record_id,))
    conn.commit()
    return {"ok": True}


def reset_learning(conn: sqlite3.Connection) -> dict:
    conn.execute("UPDATE records SET user_signal = 0")
    cur = conn.execute("DELETE FROM learning_rules")
    conn.commit()
    return {"ok": True, "rules_deleted": cur.rowcount or 0}


def list_learning_rules(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, rule_type, pattern, action, applied_count, created_at "
        "FROM learning_rules ORDER BY created_at DESC"
    ).fetchall()
    return [
        {
            "id": r[0],
            "rule_type": r[1],
            "pattern": r[2],
            "action": r[3],
            "applied_count": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def hidden_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM records WHERE user_signal = 1"
    ).fetchone()[0]


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
    except Exception:
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
