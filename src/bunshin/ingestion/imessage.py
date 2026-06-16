"""Import iMessage / SMS history from ~/Library/Messages/chat.db.

Joins messages with the handle (contact identifier) and chat (group
name) tables. Stores each message as a bunshin record with
source='imessage'.

Requires Full Disk Access for the terminal / Python process. We
surface a friendly error if the DB is unreadable.

Modern macOS (Ventura+) leaves the `text` column NULL on many messages
and stashes the content in `attributedBody` (NSAttributedString /
typedstream). We attempt a best-effort UTF-8 scan to recover text from
those blobs.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from bunshin.storage import insert_record


MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Apple epoch: 2001-01-01 UTC.
APPLE_EPOCH_OFFSET = 978307200


def _safe_copy(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    tmp = Path(tempfile.gettempdir()) / (
        f"bunshin-imessage-{int(datetime.now().timestamp())}.db"
    )
    try:
        shutil.copy2(path, tmp)
        for ext in ("-wal", "-shm"):
            side = Path(str(path) + ext)
            if side.exists():
                shutil.copy2(side, Path(str(tmp) + ext))
        return tmp
    except (OSError, PermissionError):
        return None


# Strings shorter than this in attributedBody are likely formatting
# markers (font names, etc.) not user content.
_MIN_RECOVERED_LEN = 3

# typedstream metadata strings we never want to emit as "message text".
_NS_CLASS_FRAGMENTS = (
    "NSString",
    "NSAttributedString",
    "NSDictionary",
    "NSMutableDictionary",
    "NSArray",
    "NSMutableArray",
    "NSNumber",
    "NSObject",
    "NSColor",
    "NSFont",
    "NSParagraphStyle",
    "NSValue",
    "NSData",
    "NSDate",
    "NSURL",
    "streamtyped",
    "__kIM",
    "AttributeName",
)


def _looks_like_class_name(s: str) -> bool:
    """Detect typedstream class names / formatting metadata."""
    s = s.strip()
    if not s:
        return True
    for frag in _NS_CLASS_FRAGMENTS:
        if frag in s:
            return True
    # Short pure-ASCII identifiers (no spaces, no Japanese) are almost
    # always class / attribute names rather than message text.
    if len(s) < 40 and re.fullmatch(r"[@_$A-Za-z0-9.]+", s):
        return True
    return False


def _recover_text_from_attributedbody(blob: bytes) -> Optional[str]:
    """Best-effort UTF-8 scan over the NSAttributedString blob.

    The text content is embedded as a length-prefixed UTF-8 string after
    a `NSString` class marker. We pick the longest plausible string in
    the blob — far from perfect but recovers the message body in the
    vast majority of cases.
    """
    if not blob:
        return None
    # iMessage's typedstream encodes the user-visible text early; we
    # look for the marker `NSString` and pull text following it. Falling
    # back to the longest UTF-8 run if the marker isn't found.
    try:
        marker = b"NSString"
        idx = blob.find(marker)
        candidates: list[str] = []
        if idx != -1:
            tail = blob[idx + len(marker):]
            # Skip a few bytes of metadata then try to decode.
            for offset in range(0, 32):
                chunk = tail[offset:offset + 8192]
                try:
                    decoded = chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                for part in re.split(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", decoded):
                    if len(part) >= _MIN_RECOVERED_LEN:
                        candidates.append(part)
        # Always also scan whole blob for safety.
        whole = blob.decode("utf-8", errors="ignore")
        for part in re.split(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", whole):
            if len(part) >= _MIN_RECOVERED_LEN:
                candidates.append(part)
        if not candidates:
            return None
        candidates = [c for c in candidates if not _looks_like_class_name(c)]
        if not candidates:
            return None
        # Pick the longest remaining candidate — almost always the
        # message body.
        best = max(candidates, key=len).strip()
        return best if len(best) >= _MIN_RECOVERED_LEN else None
    except Exception:
        return None


def _apple_date_to_unix(apple_date: int) -> Optional[int]:
    """Convert chat.db date to Unix timestamp.

    macOS >= 10.13 uses nanoseconds since Apple epoch.
    macOS <= 10.12 used seconds since Apple epoch.
    """
    if not apple_date:
        return None
    if apple_date > 10**12:  # nanoseconds
        return int(apple_date / 1_000_000_000 + APPLE_EPOCH_OFFSET)
    return int(apple_date + APPLE_EPOCH_OFFSET)


def _get_last_ts(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?", ("imessage_last_ts",)
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_ts(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        ("imessage_last_ts", str(ts)),
    )


def import_imessage(
    conn: sqlite3.Connection,
    initial_days: int = 365,
    verbose: bool = False,
) -> dict:
    """Import iMessage / SMS history. Incremental from last seen ts."""
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats: dict = {
        "scanned": 0,
        "inserted": 0,
        "skipped_no_text": 0,
        "recovered_from_blob": 0,
        "error": None,
    }

    snap = _safe_copy(MESSAGES_DB)
    if not snap:
        stats["error"] = (
            "Messages の DB を読めません。"
            "システム設定 → プライバシーとセキュリティ → "
            "フルディスクアクセス → ターミナル（または Python）"
            "を有効にしてください。"
        )
        return stats

    last_ts = _get_last_ts(conn)
    if last_ts is None:
        last_ts = int(datetime.now().timestamp()) - initial_days * 86400
    threshold_apple = (last_ts - APPLE_EPOCH_OFFSET) * 1_000_000_000

    msg_conn = None
    try:
        msg_conn = sqlite3.connect(snap)
        msg_conn.row_factory = sqlite3.Row

        sql = """
            SELECT
                m.ROWID         AS rowid,
                m.text          AS text,
                m.attributedBody AS attributedBody,
                m.is_from_me    AS is_from_me,
                m.date          AS date,
                m.service       AS service,
                h.id            AS handle_id,
                c.display_name  AS chat_name,
                c.chat_identifier AS chat_identifier
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.date >= ?
            ORDER BY m.date ASC
        """
        cur = msg_conn.execute(sql, (threshold_apple,))
        latest_seen = last_ts

        for row in cur:
            stats["scanned"] += 1
            text = (row["text"] or "").strip()
            if not text and row["attributedBody"]:
                recovered = _recover_text_from_attributedbody(row["attributedBody"])
                if recovered:
                    text = recovered
                    stats["recovered_from_blob"] += 1
            if not text:
                stats["skipped_no_text"] += 1
                continue

            unix_ts = _apple_date_to_unix(row["date"])
            if unix_ts is None:
                continue
            if unix_ts > latest_seen:
                latest_seen = unix_ts

            sender = "me" if row["is_from_me"] else (row["handle_id"] or "unknown")
            chat_name = row["chat_name"] or ""
            chat_id = row["chat_identifier"] or ""
            service = row["service"] or "iMessage"
            date_str = datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M")

            header = f"[{service}] {date_str}"
            chat_label = chat_name or (
                chat_id if chat_id and chat_id != row["handle_id"] else ""
            )
            if chat_label:
                header += f" {chat_label}"

            content = f"{header}\n{sender}: {text}"
            source_id = f"imessage:{row['rowid']}"
            rid = insert_record(
                conn,
                source="imessage",
                timestamp=unix_ts,
                content=content,
                source_id=source_id,
                metadata={
                    "service": service,
                    "from_me": bool(row["is_from_me"]),
                    "contact": row["handle_id"],
                    "chat_name": chat_name,
                    "chat_id": chat_id,
                },
            )
            if rid:
                stats["inserted"] += 1
                if verbose and stats["inserted"] % 100 == 0:
                    print(f"…{stats['inserted']} messages")

        if stats["scanned"] > 0:
            _set_last_ts(conn, latest_seen)
            conn.commit()
    finally:
        if msg_conn is not None:
            try:
                msg_conn.close()
            except Exception:
                pass
        try:
            snap.unlink()
            for ext in ("-wal", "-shm"):
                side = Path(str(snap) + ext)
                if side.exists():
                    side.unlink()
        except OSError:
            pass

    return stats
