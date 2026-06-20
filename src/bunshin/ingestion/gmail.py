"""Import Gmail messages via IMAP using an App Password.

Setup:
  1. Enable 2FA on your Google account
  2. Generate app password: https://myaccount.google.com/apppasswords
  3. Run: bunshin setup-gmail --email you@gmail.com
"""
import email
import email.policy
import email.utils
import imaplib
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from bunshin.storage import insert_record


GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
CONFIG_PATH = Path.home() / ".bunshin" / "gmail.json"
CHUNK_SIZE = 1500
DEFAULT_FOLDER = '"[Gmail]/All Mail"'


def save_credentials(email_addr: str, app_password: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"email": email_addr, "app_password": app_password})
    )
    CONFIG_PATH.chmod(0o600)


def load_credentials() -> Optional[dict]:
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _html_to_text(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(msg) -> str:
    """Best-effort plain text extraction from RFC822 message."""
    if msg.is_multipart():
        text_parts = []
        html_parts = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    text_parts.append(part.get_content())
                except (LookupError, UnicodeDecodeError, KeyError):
                    pass
            elif ctype == "text/html":
                try:
                    html_parts.append(part.get_content())
                except (LookupError, UnicodeDecodeError, KeyError):
                    pass
        if text_parts:
            return "\n\n".join(p for p in text_parts if p).strip()
        if html_parts:
            return "\n\n".join(_html_to_text(h) for h in html_parts if h).strip()
        return ""
    try:
        content = msg.get_content()
        if msg.get_content_type() == "text/html":
            return _html_to_text(content)
        return (content or "").strip()
    except (LookupError, UnicodeDecodeError, KeyError):
        return ""


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            window_start = max(end - 200, start + 100)
            br = text.rfind("\n\n", window_start, end)
            if br != -1:
                end = br + 2
            else:
                br = text.rfind("\n", window_start, end)
                if br != -1:
                    end = br + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - 100, start + 1)
    return chunks


def _get_last_date(conn: sqlite3.Connection) -> Optional[str]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("gmail_last_date",),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _set_last_date(conn: sqlite3.Connection, date_str: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        ("gmail_last_date", date_str),
    )


def import_gmail(
    conn: sqlite3.Connection,
    email_addr: str,
    app_password: str,
    folder: str = DEFAULT_FOLDER,
    limit: Optional[int] = None,
    initial_days: int = 90,
    verbose: bool = False,
    full: bool = False,
) -> dict:
    """Connect to Gmail via IMAP, fetch new emails since last run, index them.

    First run: fetches last `initial_days` days.
    Subsequent runs: fetches since last successful import date.
    Pass `full=True` to ignore the last-sync marker and refetch from
    `initial_days` ago — used when the user wants to backfill history.
    """
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "fetched": 0,
        "imported": 0,
        "chunks_inserted": 0,
        "errors": 0,
        "error_msg": None,
    }

    try:
        M = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
    except OSError as e:
        stats["error_msg"] = f"Cannot connect: {e}"
        return stats

    try:
        try:
            M.login(email_addr, app_password)
        except imaplib.IMAP4.error as e:
            stats["error_msg"] = (
                f"Login failed: {e}. "
                "Make sure you used an APP PASSWORD (not your regular password). "
                "Generate one at https://myaccount.google.com/apppasswords"
            )
            return stats

        status, _ = M.select(folder, readonly=True)
        if status != "OK":
            stats["error_msg"] = f"Cannot select folder {folder}"
            return stats

        last_date = None if full else _get_last_date(conn)
        if last_date:
            search_criteria = f'(SINCE "{last_date}")'
        else:
            since = (datetime.now() - timedelta(days=initial_days)).strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{since}")'

        status, data = M.search(None, search_criteria)
        if status != "OK":
            stats["error_msg"] = "Search failed"
            return stats

        uids = data[0].split() if data and data[0] else []
        if limit:
            uids = uids[-limit:]
        stats["fetched"] = len(uids)

        latest_date_obj = None

        for uid in uids:
            try:
                status, msg_data = M.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    stats["errors"] += 1
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw, policy=email.policy.default)

                subject = str(msg.get("Subject", ""))
                from_addr = str(msg.get("From", ""))
                date_str = str(msg.get("Date", ""))
                timestamp = 0
                try:
                    date_obj = email.utils.parsedate_to_datetime(date_str)
                    if date_obj:
                        timestamp = int(date_obj.timestamp())
                        if latest_date_obj is None or date_obj > latest_date_obj:
                            latest_date_obj = date_obj
                except (TypeError, ValueError):
                    pass

                body = _extract_body(msg)
                if not body:
                    continue

                full_text = (
                    f"Subject: {subject}\n"
                    f"From: {from_addr}\n"
                    f"Date: {date_str}\n\n"
                    f"{body}"
                )
                chunks = _chunk_text(full_text)
                message_id = str(msg.get("Message-ID", f"uid:{uid.decode()}"))

                for i, chunk in enumerate(chunks):
                    insert_record(
                        conn,
                        source="gmail",
                        timestamp=timestamp,
                        content=chunk,
                        source_id=message_id,
                        metadata={
                            "subject": subject[:300],
                            "from": from_addr[:300],
                            "date": date_str[:80],
                            "chunk_index": i,
                            "chunk_count": len(chunks),
                        },
                    )
                    stats["chunks_inserted"] += 1
                stats["imported"] += 1

                if verbose and stats["imported"] % 20 == 0:
                    print(f"  Imported {stats['imported']} emails...")
            except Exception as e:
                stats["errors"] += 1
                if verbose:
                    print(f"Error on uid {uid}: {e}")

        if latest_date_obj:
            # +1 day so SINCE next time doesn't refetch the same day
            next_date = (latest_date_obj + timedelta(days=1)).strftime("%d-%b-%Y")
            _set_last_date(conn, next_date)
        conn.commit()
    finally:
        try:
            M.close()
        except Exception:
            pass
        try:
            M.logout()
        except Exception:
            pass

    return stats
