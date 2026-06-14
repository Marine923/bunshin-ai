"""Import calendar events from a public iCal URL (Google Calendar private feed).

Setup:
  1. Google Calendar → Settings → Calendars → 統合
  2. Copy "カレンダーの非公開URL（iCal形式）"
  3. Run: bunshin setup-calendar URL
"""
import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import httpx
from icalendar import Calendar

from bunshin.storage import insert_record


CONFIG_PATH = Path.home() / ".bunshin" / "calendar.json"


def save_url(url: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"url": url}))
    CONFIG_PATH.chmod(0o600)


def load_url() -> Optional[str]:
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text()).get("url")
    except (json.JSONDecodeError, OSError):
        return None


def _fetch_ics(url: str) -> str:
    r = httpx.get(url, timeout=30.0, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _normalize_dt(dt) -> tuple[int, str]:
    """Convert ical date/datetime to (unix_ts, readable_str)."""
    if dt is None:
        return 0, ""
    if isinstance(dt, datetime):
        try:
            return int(dt.timestamp()), dt.strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return 0, dt.isoformat()
    if isinstance(dt, date):
        try:
            d = datetime.combine(dt, datetime.min.time())
            return int(d.timestamp()), dt.strftime("%Y-%m-%d (終日)")
        except (OSError, OverflowError, ValueError):
            return 0, dt.isoformat()
    return 0, str(dt)


def _parse_events(ics_text: str) -> list[dict]:
    cal = Calendar.from_ical(ics_text)
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        summary = str(component.get("summary", "") or "")
        description = str(component.get("description", "") or "")
        location = str(component.get("location", "") or "")
        organizer = str(component.get("organizer", "") or "")
        uid = str(component.get("uid", "") or "")

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        start_ts, start_str = _normalize_dt(dtstart.dt if dtstart else None)
        _, end_str = _normalize_dt(dtend.dt if dtend else None)

        if not summary and not description:
            continue

        events.append(
            {
                "uid": uid,
                "timestamp": start_ts,
                "summary": summary,
                "description": description,
                "location": location,
                "organizer": organizer,
                "start": start_str,
                "end": end_str,
            }
        )
    return events


def _delete_existing(conn: sqlite3.Connection) -> None:
    """Wipe all calendar records (idempotent re-import)."""
    cursor = conn.execute("SELECT id FROM records WHERE source = 'calendar'")
    ids = [row[0] for row in cursor.fetchall()]
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    try:
        conn.execute(f"DELETE FROM records_vec WHERE record_id IN ({placeholders})", ids)
    except sqlite3.OperationalError:
        pass
    conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", ids)


def import_calendar(
    conn: sqlite3.Connection,
    url: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """Fetch ICS feed and import events. Idempotent — wipes & rebuilds."""
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {"fetched": 0, "imported": 0, "errors": 0, "error_msg": None}

    if not url:
        url = load_url()
    if not url:
        stats["error_msg"] = "No calendar URL configured. Run setup-calendar first."
        return stats

    try:
        ics = _fetch_ics(url)
    except (httpx.HTTPError, httpx.RequestError) as e:
        stats["error_msg"] = f"Fetch failed: {e}"
        return stats

    try:
        events = _parse_events(ics)
    except Exception as e:
        stats["error_msg"] = f"Parse failed: {e}"
        return stats

    stats["fetched"] = len(events)
    if not events:
        return stats

    _delete_existing(conn)

    for event in events:
        parts = [f"📅 {event['summary']}"] if event["summary"] else []
        if event["start"]:
            parts.append(f"日時: {event['start']}" + (f" 〜 {event['end']}" if event["end"] else ""))
        if event["location"]:
            parts.append(f"場所: {event['location']}")
        if event["organizer"]:
            parts.append(f"主催: {event['organizer']}")
        if event["description"]:
            parts.append("")
            parts.append(event["description"])
        content = "\n".join(parts)

        record_id = insert_record(
            conn,
            source="calendar",
            timestamp=event["timestamp"],
            content=content,
            source_id=f"cal:{event['uid']}" if event["uid"] else f"cal:{event['timestamp']}",
            metadata={
                "summary": event["summary"][:200],
                "location": event["location"][:200],
                "start": event["start"],
                "end": event["end"],
                "organizer": event["organizer"][:200],
            },
        )
        if record_id:
            stats["imported"] += 1
        else:
            stats["errors"] += 1

    conn.commit()
    return stats
