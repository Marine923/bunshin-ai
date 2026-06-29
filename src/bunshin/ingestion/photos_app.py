"""Import photos from the Photos.app library via AppleScript.

Photos.app stores its library at ~/Pictures/Photos Library.photoslibrary,
a sandboxed bundle Bunshin can't open directly. Instead we talk to
Photos.app over Apple Events:

  1. Pull a metadata stream (id, filename, date, GPS, album titles).
  2. Optionally export each media item to a temp dir and feed it through
     the existing EXIF + Vision OCR pipeline.

Each media item becomes a `source='photos_app'` record with
content shaped for date / place / album searches.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from bunshin.storage import insert_record


# Cap how many items we round-trip through Photos.app in one batch.
# Large batches blow up Apple Events memory; small batches are slower but
# survive multi-hour libraries.
_METADATA_BATCH = 200
_EXPORT_BATCH = 20

_DELIM_FIELD = "<<<BUNSHIN_FIELD>>>"
_DELIM_ITEM = "<<<BUNSHIN_ITEM_END>>>"


def _build_count_script() -> str:
    return '''
tell application "Photos"
    return (count of every media item) as string
end tell
'''


# Per-item property reads are ~10/sec over Apple Events, so big libraries
# need batching to surface progress. We slice `every media item` by index
# and run one osascript invocation per batch.
def _build_listing_script(offset: int = 0, batch_size: int = 200) -> str:
    start_idx = offset + 1
    end_idx = offset + batch_size
    return f'''
tell application "Photos"
    set fieldDelim to "{_DELIM_FIELD}"
    set itemDelim to "{_DELIM_ITEM}"
    set results to {{}}
    set theItems to every media item
    set total to count of theItems
    set startIdx to {start_idx}
    set endIdx to {end_idx}
    if startIdx > total then return ""
    if endIdx > total then set endIdx to total
    repeat with i from startIdx to endIdx
        try
            set theItem to item i of theItems
            set theId to id of theItem as string
            set theName to (filename of theItem) as string
            set theDate to (date of theItem) as string
            set theLat to ""
            set theLon to ""
            try
                set loc to location of theItem
                if loc is not missing value then
                    set theLat to (item 1 of loc) as string
                    set theLon to (item 2 of loc) as string
                end if
            end try
            set lineOut to theId & fieldDelim & theName & fieldDelim & theDate & fieldDelim & theLat & fieldDelim & theLon
            copy lineOut to end of results
        end try
    end repeat
    set AppleScript's text item delimiters to itemDelim
    return results as string
end tell
'''


def _build_album_map_script() -> str:
    """One-shot AppleScript that emits {album_name}\\t{photo_id} per line
    for every album × media item. Cheaper than asking each item for its
    albums (per-item Apple Events round trips dominate)."""
    return f'''
tell application "Photos"
    set fieldDelim to "{_DELIM_FIELD}"
    set lineDelim to "{_DELIM_ITEM}"
    set out to {{}}
    try
        set theAlbums to every album
    on error
        return ""
    end try
    repeat with anAlbum in theAlbums
        try
            set albumName to (name of anAlbum) as string
            set itemsInAlbum to media items of anAlbum
            repeat with anItem in itemsInAlbum
                try
                    set itemId to (id of anItem) as string
                    copy (albumName & fieldDelim & itemId) to end of out
                end try
            end repeat
        end try
    end repeat
    set AppleScript's text item delimiters to lineDelim
    return out as string
end tell
'''


def _build_album_map() -> dict[str, list[str]]:
    """v0.10.5 (B4): photo_id → [album_name, ...] map.

    Returns {} if AppleScript fails or no albums exist; callers must
    handle the empty case (the importer just skips the album line then).
    """
    raw = _run_applescript(_build_album_map_script(), timeout=600)
    if not raw or not raw.strip():
        return {}
    out: dict[str, list[str]] = {}
    for line in raw.split(_DELIM_ITEM):
        line = line.strip()
        if not line or _DELIM_FIELD not in line:
            continue
        parts = line.split(_DELIM_FIELD, 1)
        if len(parts) != 2:
            continue
        album_name, photo_id = parts[0].strip(), parts[1].strip()
        if not album_name or not photo_id:
            continue
        out.setdefault(photo_id, []).append(album_name)
    return out


def _count_total_items() -> Optional[int]:
    raw = _run_applescript(_build_count_script(), timeout=60)
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _run_applescript(script: str, timeout: int = 1800) -> Optional[str]:
    """Feed the script via stdin — `-e` has argv length limits and is
    flaky with the special chars Photos.app's listing script uses."""
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _parse_applescript_date(s: str) -> Optional[int]:
    """Same locale-handling logic as the Notes ingester."""
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


def parse_listing(raw: str) -> list[dict]:
    items: list[dict] = []
    for block in raw.split(_DELIM_ITEM):
        block = block.strip()
        if not block:
            continue
        parts = block.split(_DELIM_FIELD)
        if len(parts) < 5:
            continue
        item_id, name, date_str, lat, lon = (p.strip() for p in parts[:5])
        try:
            lat_f = float(lat) if lat else None
        except ValueError:
            lat_f = None
        try:
            lon_f = float(lon) if lon else None
        except ValueError:
            lon_f = None
        items.append({
            "id": item_id,
            "name": name,
            "date": _parse_applescript_date(date_str),
            "lat": lat_f,
            "lon": lon_f,
            "favorite": False,
            "kind": "",
        })
    return items


def _get_last_seen(conn: sqlite3.Connection, item_id: str) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"photos_app:{item_id}",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_seen(conn: sqlite3.Connection, item_id: str, ts: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"photos_app:{item_id}", str(ts)),
    )


def _export_items_to_temp(item_ids: list[str], dest: Path) -> dict[str, Path]:
    """Ask Photos.app to export the given items as originals into `dest`.

    Returns a mapping {item_id: exported_path}. Items Photos.app can't
    export (live photos with missing originals, etc.) are simply omitted.
    """
    if not item_ids:
        return {}
    dest.mkdir(parents=True, exist_ok=True)
    id_list = ", ".join(f'"{i}"' for i in item_ids)
    script = f'''
tell application "Photos"
    set destFolder to POSIX file "{dest}" as alias
    set targetIds to {{{id_list}}}
    set targets to {{}}
    repeat with anId in targetIds
        try
            set m to media item id (anId as string)
            copy m to end of targets
        end try
    end repeat
    if (count of targets) > 0 then
        export targets to destFolder with using originals
    end if
end tell
'''
    _run_applescript(script, timeout=600)
    # Photos.app names the exports after the original filename; match by
    # what currently sits in dest. Photos may also produce sidecar files
    # (e.g. live photo .mov) — we keep the largest matching extension per
    # base name.
    out: dict[str, Path] = {}
    files = sorted(dest.iterdir())
    # Map by basename → path; later assignment from item id happens at
    # the call site via filename match.
    return {p.name: p for p in files if p.is_file()}  # type: ignore[return-value]


def import_photos_app(
    conn: sqlite3.Connection,
    limit: int = 0,
    days: int = 0,
    with_ocr: bool = False,
    verbose: bool = False,
) -> dict:
    """Import items from Photos.app.

    Args:
        limit: cap at this many items (0 = all).
        days: only items dated within the last N days (0 = all).
        with_ocr: export originals and run EXIF + Vision OCR on each.
                  Much slower; off by default.

    Returns: scanned, imported, unchanged, with_gps, with_ocr, failed.
    """
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "scanned": 0,
        "imported": 0,
        "unchanged": 0,
        "with_gps": 0,
        "with_ocr": 0,
        "failed": 0,
        "applescript_failed": False,
    }

    total = _count_total_items()
    if total is None:
        stats["applescript_failed"] = True
        return stats
    if verbose:
        print(f"Photos.app library: {total} items")

    # Pull metadata in batches so each osascript invocation completes in
    # bounded time and we can surface progress to the user.
    cap = limit if limit > 0 else total
    items: list[dict] = []
    offset = 0
    while offset < total and len(items) < cap:
        this_batch = min(_METADATA_BATCH, cap - len(items))
        raw = _run_applescript(
            _build_listing_script(offset=offset, batch_size=this_batch),
            timeout=300,
        )
        if raw is None:
            stats["applescript_failed"] = True
            return stats
        batch = parse_listing(raw)
        if not batch:
            break
        items.extend(batch)
        offset += this_batch
        if verbose:
            print(f"  Listed {len(items)} / {min(cap, total)} items")

    # v0.10.5 (B4 写真ライブラリ深堀り): collect photo_id → albums map
    # so search hits like "壱岐黄金 アルバム" or "2026 旅行 ハワイ"
    # surface the right items.
    album_map: dict[str, list[str]] = _build_album_map()
    if verbose:
        if album_map:
            in_album_count = sum(1 for it in items if it["id"] in album_map)
            print(f"Albums: {len(set().union(*album_map.values())) if album_map else 0} unique, "
                  f"{in_album_count} of these items are in ≥1 album")
        else:
            print("Albums: none (or AppleScript failed to read)")

    # Day-side filter in Python (AppleScript date comparisons are fragile
    # across locales)
    if days > 0:
        now = int(datetime.now().timestamp())
        cutoff = now - days * 86400
        items = [it for it in items if it["date"] and it["date"] >= cutoff]
    if verbose:
        print(f"Photos.app to process: {len(items)} items")

    # Optional OCR pass: export in batches, run OCR.
    # We collect per-item exported paths into ocr_by_id.
    ocr_by_id: dict[str, str] = {}
    if with_ocr and items:
        from bunshin.ingestion.photos import ocr_batch
        # Need only items we'll actually re-import (mtime newer than last seen).
        fresh = [
            it for it in items
            if it["date"] is None
            or _get_last_seen(conn, it["id"]) is None
            or _get_last_seen(conn, it["id"]) < it["date"]
        ]
        for i in range(0, len(fresh), _EXPORT_BATCH):
            batch = fresh[i:i + _EXPORT_BATCH]
            with tempfile.TemporaryDirectory(prefix="bunshin-photos-") as td:
                td_path = Path(td)
                exported = _export_items_to_temp([it["id"] for it in batch], td_path)
                if not exported:
                    continue
                # Match exported files back to items by filename.
                paths_for_ocr: list[Path] = []
                name_to_id: dict[str, str] = {}
                for it in batch:
                    # Some items get sidecars; match by basename stem.
                    stem = Path(it["name"]).stem
                    for fname, fpath in exported.items():
                        if Path(fname).stem == stem:
                            paths_for_ocr.append(fpath)
                            name_to_id[fname] = it["id"]
                            break
                if not paths_for_ocr:
                    continue
                ocr_results = ocr_batch(paths_for_ocr)
                for fname, item_id in name_to_id.items():
                    fpath_str = str(td_path / fname)
                    if fpath_str in ocr_results:
                        ocr_by_id[item_id] = ocr_results[fpath_str]
            if verbose:
                print(f"  OCR: {min(i+_EXPORT_BATCH, len(fresh))}/{len(fresh)}")

    for item in items:
        stats["scanned"] += 1
        item_id = item["id"]
        item_ts = item["date"] or int(datetime.now().timestamp())

        last = _get_last_seen(conn, item_id)
        if last is not None and last >= item_ts:
            stats["unchanged"] += 1
            continue

        if item["lat"] is not None and item["lon"] is not None:
            stats["with_gps"] += 1
        ocr_text = ocr_by_id.get(item_id, "")
        if ocr_text:
            stats["with_ocr"] += 1

        date_str = (
            datetime.fromtimestamp(item_ts).strftime("%Y-%m-%d")
            if item_ts else ""
        )
        header_parts = ["[photos_app]", date_str]
        if item["lat"] is not None and item["lon"] is not None:
            header_parts.append(f"({item['lat']:.4f},{item['lon']:.4f})")
        if item["favorite"]:
            header_parts.append("⭐")
        header_parts.append(item["name"])
        header = " ".join(p for p in header_parts if p)

        albums_for_item = album_map.get(item_id, [])

        body_parts = []
        if albums_for_item:
            body_parts.append("アルバム: " + " / ".join(albums_for_item))
        if ocr_text:
            body_parts.append(ocr_text)
        body = "\n".join(body_parts) if body_parts else "(no text recognized)"
        content = f"{header}\n{body}".strip()

        rid = insert_record(
            conn,
            source="photos_app",
            timestamp=item_ts,
            content=content,
            source_id=item_id,
            metadata={
                "photos_id": item_id,
                "name": item["name"],
                "date": item["date"],
                "lat": item["lat"],
                "lon": item["lon"],
                "favorite": item["favorite"],
                "kind": item["kind"],
                "ocr_chars": len(ocr_text),
                "albums": albums_for_item,
            },
        )
        if rid:
            stats["imported"] += 1
            _set_last_seen(conn, item_id, item_ts)
            conn.commit()
            if verbose and stats["imported"] % 50 == 0:
                print(f"…{stats['imported']} items")

    return stats
