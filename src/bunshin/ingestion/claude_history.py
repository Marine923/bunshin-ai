"""Import Claude Code transcript history into Bunshin storage.

Messages within a session are grouped into ~1500-char "turns" so each record
contains question + answer pairs instead of single fragments.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from bunshin.storage import insert_record


CHUNK_SIZE = 1500  # chars per chunk


def find_transcript_files(claude_projects_dir: Path) -> Iterator[Path]:
    if not claude_projects_dir.exists():
        return
    yield from claude_projects_dir.rglob("*.jsonl")


def parse_transcript_line(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def extract_text(msg: dict) -> Optional[str]:
    content = msg.get("content")
    if content is None and "message" in msg:
        content = msg["message"].get("content") if isinstance(msg["message"], dict) else None
    if content is None:
        return None
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        texts.append(text)
                elif block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    texts.append(f"[tool_use: {name}]")
        return "\n".join(texts).strip() or None
    return None


def extract_timestamp(msg: dict) -> int:
    ts = msg.get("timestamp")
    if ts is None and "message" in msg and isinstance(msg["message"], dict):
        ts = msg["message"].get("timestamp")
    if isinstance(ts, (int, float)):
        return int(ts) if ts < 1e12 else int(ts / 1000)
    if isinstance(ts, str):
        try:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return 0
    return 0


def extract_role(msg: dict) -> Optional[str]:
    role = msg.get("type") or msg.get("role")
    if role is None and "message" in msg and isinstance(msg["message"], dict):
        role = msg["message"].get("role")
    return role


def _load_session_messages(jsonl_path: Path) -> list[dict]:
    """Read all messages from a session, sorted by timestamp."""
    messages = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = parse_transcript_line(line)
                if not msg:
                    continue
                text = extract_text(msg)
                if not text:
                    continue
                messages.append(
                    {
                        "text": text,
                        "role": extract_role(msg),
                        "timestamp": extract_timestamp(msg),
                    }
                )
    except (OSError, UnicodeDecodeError):
        return []
    messages.sort(key=lambda m: m["timestamp"])
    return messages


def chunk_messages(messages: list[dict], chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """Group consecutive messages into ~chunk_size character turns."""
    chunks = []
    current: list[dict] = []
    current_len = 0

    for msg in messages:
        msg_block = f"[{msg['role'] or '?'}] {msg['text']}"
        block_len = len(msg_block)
        # If adding this would exceed and we already have content, flush
        if current and current_len + block_len > chunk_size:
            chunks.append(_build_chunk(current))
            current = [msg]
            current_len = block_len
        else:
            current.append(msg)
            current_len += block_len + 4  # buffer for joiner

    if current:
        chunks.append(_build_chunk(current))
    return chunks


def _build_chunk(messages: list[dict]) -> dict:
    content = "\n\n".join(f"[{m['role'] or '?'}] {m['text']}" for m in messages)
    return {
        "timestamp": messages[0]["timestamp"],
        "content": content,
        "roles": [m["role"] for m in messages],
        "message_count": len(messages),
    }


def _delete_session_records(conn: sqlite3.Connection, source_id: str) -> None:
    cursor = conn.execute(
        "SELECT id FROM records WHERE source = 'claude' AND source_id = ?",
        (source_id,),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    try:
        conn.execute(f"DELETE FROM records_vec WHERE record_id IN ({placeholders})", ids)
    except sqlite3.OperationalError:
        pass
    conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", ids)


def _get_last_mtime(conn: sqlite3.Connection, source_id: str) -> Optional[int]:
    cursor = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"claude_mtime:{source_id}",),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def _set_last_mtime(conn: sqlite3.Connection, source_id: str, mtime: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"claude_mtime:{source_id}", str(mtime)),
    )


def import_claude_history(
    conn: sqlite3.Connection,
    claude_projects_dir: Path,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """Import all Claude transcripts, grouping messages into turns.

    Sessions are skipped if their jsonl mtime hasn't changed since last import.
    Pass force=True to bypass and reindex all.
    """
    # Load vec extension so _delete_session_records can clean up old vectors
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "files_scanned": 0,
        "files_unchanged": 0,
        "files_reimported": 0,
        "files_failed": 0,
        "records_inserted": 0,
        "records_skipped": 0,
    }

    for jsonl_path in find_transcript_files(claude_projects_dir):
        stats["files_scanned"] += 1
        source_id = str(jsonl_path)

        try:
            current_mtime = int(jsonl_path.stat().st_mtime)
        except OSError:
            stats["files_failed"] += 1
            continue

        last_mtime = _get_last_mtime(conn, source_id)
        if not force and last_mtime is not None and last_mtime >= current_mtime:
            stats["files_unchanged"] += 1
            continue

        messages = _load_session_messages(jsonl_path)
        if not messages:
            stats["files_failed"] += 1
            continue

        # Wipe and re-chunk this session
        _delete_session_records(conn, source_id)
        chunks = chunk_messages(messages)

        try:
            rel_session = (
                str(jsonl_path.relative_to(claude_projects_dir))
                if jsonl_path.is_relative_to(claude_projects_dir)
                else str(jsonl_path)
            )
        except (ValueError, AttributeError):
            rel_session = str(jsonl_path)

        for chunk in chunks:
            record_id = insert_record(
                conn,
                source="claude",
                timestamp=chunk["timestamp"],
                content=chunk["content"],
                source_id=source_id,
                metadata={
                    "session_file": rel_session,
                    "message_count": chunk["message_count"],
                    "roles": chunk["roles"],
                },
            )
            if record_id:
                stats["records_inserted"] += 1
            else:
                stats["records_skipped"] += 1

        _set_last_mtime(conn, source_id, current_mtime)
        conn.commit()
        stats["files_reimported"] += 1

        if verbose:
            print(f"Reimported: {jsonl_path} ({len(chunks)} chunks)")

    return stats
