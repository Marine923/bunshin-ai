"""Persistent chat sessions for Bunshin.

Stores chat sessions and individual messages so the user can:
  - resume a past conversation with full context
  - browse and search their chat history (eventually)
  - have multi-turn dialogues that remember earlier turns

Schema:
  chat_sessions(id, title, model, created_at, updated_at)
  chat_messages(id, session_id, role, content, context_used, created_at)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    model       TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    role         TEXT NOT NULL,        -- 'user' | 'assistant'
    content      TEXT NOT NULL,
    context_used TEXT,                  -- JSON list of referenced memory records
    created_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at);
"""


def init_chat_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> int:
    return int(datetime.now().timestamp())


def create_session(
    conn: sqlite3.Connection,
    title: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Create a new chat session. Returns the new session id."""
    init_chat_schema(conn)
    sid = str(uuid.uuid4())
    now = _now()
    conn.execute(
        "INSERT INTO chat_sessions(id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (sid, title, model, now, now),
    )
    conn.commit()
    return sid


def get_session(conn: sqlite3.Connection, session_id: str) -> Optional[dict]:
    init_chat_schema(conn)
    cursor = conn.execute(
        "SELECT id, title, model, created_at, updated_at FROM chat_sessions WHERE id = ?",
        (session_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "title": row[1],
        "model": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


def list_sessions(
    conn: sqlite3.Connection,
    limit: int = 50,
    query: str | None = None,
) -> list[dict]:
    """Return most-recently-updated sessions with message counts.

    If `query` is provided, only sessions whose title or any message
    content matches (case-insensitive substring) are returned.
    """
    init_chat_schema(conn)
    params: list = []
    where = ""
    if query and query.strip():
        like = f"%{query.strip().lower()}%"
        where = (
            " WHERE LOWER(s.title) LIKE ? "
            " OR s.id IN (SELECT DISTINCT session_id FROM chat_messages "
            "             WHERE LOWER(content) LIKE ?)"
        )
        params = [like, like]
    sql = (
        "SELECT s.id, s.title, s.model, s.created_at, s.updated_at,"
        "       COUNT(m.id) AS message_count,"
        "       (SELECT content FROM chat_messages WHERE session_id = s.id "
        "        AND role = 'user' ORDER BY id ASC LIMIT 1) AS first_user_msg, "
        "       (SELECT content FROM chat_messages WHERE session_id = s.id "
        "        ORDER BY id DESC LIMIT 1) AS last_msg "
        "FROM chat_sessions s "
        "LEFT JOIN chat_messages m ON m.session_id = s.id"
        + where +
        " GROUP BY s.id "
        " ORDER BY s.updated_at DESC "
        " LIMIT ?"
    )
    params.append(limit)
    cursor = conn.execute(sql, params)
    out = []
    for r in cursor.fetchall():
        title = r[1]
        if not title and r[6]:
            # Derive a title from the first user message
            title = (r[6][:48] + "…") if len(r[6]) > 48 else r[6]
        last = (r[7] or "").strip().replace("\n", " ")
        preview = (last[:80] + "…") if len(last) > 80 else last
        out.append({
            "id": r[0],
            "title": title or "(empty)",
            "model": r[2],
            "created_at": r[3],
            "updated_at": r[4],
            "message_count": r[5],
            "preview": preview,
        })
    return out


def add_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    context_used: Optional[list[dict]] = None,
) -> int:
    """Append a message to a session and bump its updated_at."""
    init_chat_schema(conn)
    now = _now()
    cursor = conn.execute(
        """INSERT INTO chat_messages(session_id, role, content, context_used, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            session_id,
            role,
            content,
            json.dumps(context_used, ensure_ascii=False) if context_used is not None else None,
            now,
        ),
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    # Auto-title from the first user message if none set
    if role == "user":
        sess = get_session(conn, session_id)
        if sess and not sess["title"]:
            title = (content[:48] + "…") if len(content) > 48 else content
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
    conn.commit()
    return cursor.lastrowid


def get_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    init_chat_schema(conn)
    cursor = conn.execute(
        """SELECT id, role, content, context_used, created_at
           FROM chat_messages
           WHERE session_id = ?
           ORDER BY id ASC""",
        (session_id,),
    )
    out = []
    for r in cursor.fetchall():
        ctx = json.loads(r[3]) if r[3] else None
        out.append({
            "id": r[0],
            "role": r[1],
            "content": r[2],
            "context_used": ctx,
            "created_at": r[4],
        })
    return out


def delete_session(conn: sqlite3.Connection, session_id: str) -> int:
    """Delete a session and all its messages. Returns # messages deleted."""
    init_chat_schema(conn)
    cur = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
    n = cur.fetchone()[0]
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    return n


def update_session_title(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    init_chat_schema(conn)
    conn.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title, _now(), session_id),
    )
    conn.commit()
