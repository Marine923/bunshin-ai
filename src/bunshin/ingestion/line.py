"""Import LINE chat history from text export.

How to export:
  LINE app → トーク画面 → 設定（⚙）→ トーク履歴を送信
  → Save as text file
  → Run: bunshin import-line path/to/export.txt
"""
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from bunshin.storage import insert_record


# Date line patterns:
#   2026/06/05(金)  (most common)
#   2026.06.05 Friday
DATE_PATTERNS = [
    re.compile(r"^(\d{4})/(\d{2})/(\d{2})\([日月火水木金土]\)$"),
    re.compile(r"^(\d{4})\.(\d{2})\.(\d{2}).*$"),
]

# Message line: HH:MM\tName\tContent
MESSAGE_RE = re.compile(r"^(\d{1,2}):(\d{2})\t([^\t]+)\t(.+)$")

# Chunk grouping target (chars per record)
CHUNK_SIZE = 1500


def parse_export(text: str) -> tuple[str, list[dict]]:
    """Parse LINE export text. Returns (title, messages)."""
    lines = text.splitlines()
    title = ""
    if lines and lines[0].startswith("[LINE]"):
        title = lines[0].strip()
    elif lines:
        title = lines[0].strip()

    messages = []
    current_date = None
    current_year = None
    current_month = None
    current_day = None

    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue

        matched_date = False
        for pat in DATE_PATTERNS:
            m = pat.match(line.strip())
            if m:
                try:
                    current_year = int(m.group(1))
                    current_month = int(m.group(2))
                    current_day = int(m.group(3))
                    current_date = f"{current_year}-{current_month:02d}-{current_day:02d}"
                except (ValueError, IndexError):
                    pass
                matched_date = True
                break
        if matched_date:
            continue

        msg = MESSAGE_RE.match(line)
        if msg and current_date:
            hh = int(msg.group(1))
            mm = int(msg.group(2))
            sender = msg.group(3).strip()
            content = msg.group(4).strip()
            try:
                ts = int(
                    datetime(current_year, current_month, current_day, hh, mm).timestamp()
                )
            except (ValueError, OSError):
                ts = 0
            messages.append({
                "timestamp": ts,
                "date": current_date,
                "time": f"{hh:02d}:{mm:02d}",
                "sender": sender,
                "content": content,
            })

    return title, messages


def chunk_messages(messages: list[dict], chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """Group consecutive messages into ~chunk_size character records."""
    if not messages:
        return []
    chunks = []
    current = []
    current_len = 0

    for m in messages:
        block = f"{m['date']} {m['time']} {m['sender']}: {m['content']}"
        if current and current_len + len(block) > chunk_size:
            chunks.append({
                "timestamp": current[0]["timestamp"],
                "content": "\n".join(
                    f"{x['date']} {x['time']} {x['sender']}: {x['content']}"
                    for x in current
                ),
                "senders": list({x["sender"] for x in current}),
                "from_date": current[0]["date"],
                "to_date": current[-1]["date"],
                "message_count": len(current),
            })
            current = [m]
            current_len = len(block)
        else:
            current.append(m)
            current_len += len(block) + 1

    if current:
        chunks.append({
            "timestamp": current[0]["timestamp"],
            "content": "\n".join(
                f"{x['date']} {x['time']} {x['sender']}: {x['content']}"
                for x in current
            ),
            "senders": list({x["sender"] for x in current}),
            "from_date": current[0]["date"],
            "to_date": current[-1]["date"],
            "message_count": len(current),
        })
    return chunks


def import_line_file(
    conn: sqlite3.Connection,
    path: Path,
    verbose: bool = False,
) -> dict:
    """Import a LINE export text file."""
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "messages_parsed": 0,
        "chunks_inserted": 0,
        "title": "",
        "error_msg": None,
    }

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="cp932")
        except (UnicodeDecodeError, OSError) as e:
            stats["error_msg"] = f"Cannot read file: {e}"
            return stats
    except OSError as e:
        stats["error_msg"] = f"Cannot read file: {e}"
        return stats

    title, messages = parse_export(text)
    stats["title"] = title
    stats["messages_parsed"] = len(messages)

    if not messages:
        stats["error_msg"] = "No messages parsed (check file format)"
        return stats

    # Use file path + title as source_id
    talk_id = hashlib.sha256(f"{path}:{title}".encode()).hexdigest()[:16]
    source_id = f"line:{talk_id}"

    # Wipe and reimport this talk
    cursor = conn.execute(
        "SELECT id FROM records WHERE source = 'line' AND source_id = ?",
        (source_id,),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        try:
            conn.execute(f"DELETE FROM records_vec WHERE record_id IN ({placeholders})", ids)
        except sqlite3.OperationalError:
            pass
        conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", ids)

    chunks = chunk_messages(messages)
    for chunk in chunks:
        record_id = insert_record(
            conn,
            source="line",
            timestamp=chunk["timestamp"],
            content=chunk["content"],
            source_id=source_id,
            metadata={
                "talk": title,
                "senders": chunk["senders"],
                "from_date": chunk["from_date"],
                "to_date": chunk["to_date"],
                "message_count": chunk["message_count"],
            },
        )
        if record_id:
            stats["chunks_inserted"] += 1

    conn.commit()
    return stats
