"""GPS-based place clustering for Photos.app records.

Buckets photos by GPS proximity (default ~1.1km grid), reverse-geocodes
each bucket via Wikipedia geosearch, and creates a `place` entity per
qualifying cluster linked to its photos via record_entities.

User-facing benefit: "○○の写真" / "壱岐島の写真" / "ハワイで撮った"
type queries surface the right images, and the relationships graph
gets concrete geo nodes (壱岐市 / 沼津市 / etc.) auto-populated from
where photos were actually taken.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Optional

import httpx

from bunshin.knowledge_graph import init_kg_schema, upsert_entity


# ~1.1km grid (0.01° ≈ 1.11km at the equator, less at high latitudes).
# Smaller buckets fragment a single trip; larger ones merge distinct
# venues. 0.01 is the sweet spot for "same neighborhood".
GRID = 0.01

# Don't make a place out of a one-off photo. 5 is a soft floor — for a
# location to be worth its own entity, you usually have at least a
# handful of photos there.
MIN_PHOTOS = 5

# Cap how many clusters we create per pass; the relationships graph
# would get noisy otherwise. Top buckets by photo count get priority.
MAX_CLUSTERS = 50

# Wikipedia geosearch radius (meters). API caps at 10km. Rely on the
# admin-area heuristic below to pick the encompassing city/county
# article from the top-10 candidates.
WIKI_RADIUS_M = 10000


def _wikipedia_place(lat: float, lon: float) -> Optional[str]:
    """Nearest Wikipedia article title within WIKI_RADIUS_M.

    Picks ja.wikipedia for coordinates inside Japan and en.wikipedia
    otherwise. Returns None on any failure — callers fall back to the
    coordinate-string place name.
    """
    in_japan = 24.0 <= lat <= 46.0 and 122.0 <= lon <= 146.0
    lang = "ja" if in_japan else "en"
    # Pull 10 candidates so the post-filter can prefer admin areas
    # (壱岐市) over nearby buildings (○○学校 / Some Hotel) which would
    # otherwise win on distance alone.
    try:
        r = httpx.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{lat}|{lon}",
                "gsradius": str(WIKI_RADIUS_M),
                "gslimit": "10",
                "format": "json",
            },
            headers={
                "User-Agent": "Bunshin/0.10 (https://github.com/Marine923/bunshin-ai)",
            },
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("query", {}).get("geosearch", [])
        if not results:
            return None

        # Admin-area heuristic. Most-preferred → least-preferred:
        #   1. JA: ends in 市 / 町 / 村 / 区 / 県 / 府 / 都
        #   2. EN: title contains City / Town / County / Province / Prefecture
        #   3. neither facility-style nor place-detail
        #   4. anything left
        import re as _re
        ja_admin_re = _re.compile(r"(市|町|村|区|県|府|都)$")
        en_admin_words = ("City", "Town", "Village", "Prefecture", "Province",
                          "County", "Region", "Municipality", "Borough", "District")
        facility_words = (
            "学校", "小学校", "中学校", "高等学校", "大学", "病院",
            "駅", "空港", "ホテル", "美術館", "博物館", "図書館",
            "水道局", "役所", "役場", "支店", "本社", "営業所", "工場",
            "School", "University", "Hotel", "Station", "Hospital",
            "Museum", "Library", "Stadium", "Park", "Bridge", "House",
            "Castle", "Tower", "Cathedral", "Church", "Temple",
        )

        ja_admin_hit = [r for r in results
                        if ja_admin_re.search(r.get("title", ""))]
        en_admin_hit = [r for r in results
                        if any(w in r.get("title", "") for w in en_admin_words)]
        non_facility = [r for r in results
                        if not any(w in r.get("title", "") for w in facility_words)]
        chosen = (ja_admin_hit or en_admin_hit or non_facility or results)[0]
        title = (chosen.get("title") or "").strip()
        return title or None
    except Exception:
        return None


def compute_place_clusters(
    conn: sqlite3.Connection,
    min_photos: int = MIN_PHOTOS,
    max_clusters: int = MAX_CLUSTERS,
    verbose: bool = False,
) -> dict:
    """Cluster GPS-tagged photos_app records into place entities."""
    init_kg_schema(conn)

    cur = conn.execute(
        "SELECT id, metadata FROM records WHERE source = 'photos_app'"
    )
    buckets: dict[tuple[float, float], list[str]] = defaultdict(list)
    for rid, meta_json in cur.fetchall():
        if not meta_json:
            continue
        try:
            meta = json.loads(meta_json)
        except (TypeError, ValueError):
            continue
        lat = meta.get("lat")
        lon = meta.get("lon")
        if lat is None or lon is None:
            continue
        try:
            flat = float(lat)
            flon = float(lon)
        except (TypeError, ValueError):
            continue
        key = (round(flat / GRID) * GRID, round(flon / GRID) * GRID)
        buckets[key].append(rid)

    if verbose:
        with_gps = sum(len(v) for v in buckets.values())
        print(f"GPS-tagged photos: {with_gps} → {len(buckets)} raw buckets")

    qualifying = sorted(
        [(k, rids) for k, rids in buckets.items() if len(rids) >= min_photos],
        key=lambda kv: -len(kv[1]),
    )[:max_clusters]

    if verbose:
        print(f"Qualifying clusters (≥{min_photos} photos): "
              f"{len(qualifying)} (capped at {max_clusters})")

    stats = {
        "buckets_total": len(buckets),
        "buckets_qualifying": len(qualifying),
        "entities_created": 0,
        "entities_reused": 0,
        "links_created": 0,
        "wikipedia_resolved": 0,
        "wikipedia_unresolved": 0,
    }

    for (lat, lon), rids in qualifying:
        wiki_name = _wikipedia_place(lat, lon)
        if wiki_name:
            place_name = wiki_name
            stats["wikipedia_resolved"] += 1
            description = (
                f"GPS座標 {lat:.4f}, {lon:.4f} 周辺で撮影した写真 "
                f"{len(rids)} 件のクラスタ (Wikipedia から逆ジオコーディング)"
            )
        else:
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            place_name = f"GPS {abs(lat):.2f}{ns} {abs(lon):.2f}{ew}"
            stats["wikipedia_unresolved"] += 1
            description = (
                f"GPS座標 {lat:.4f}, {lon:.4f} 周辺で撮影した写真 "
                f"{len(rids)} 件のクラスタ"
            )

        before = conn.execute(
            "SELECT id FROM entities WHERE name = ?", (place_name,)
        ).fetchone()
        ent_id = upsert_entity(
            conn,
            name=place_name,
            type_="place",
            description=description,
        )
        if ent_id == 0:
            continue
        if before:
            stats["entities_reused"] += 1
        else:
            stats["entities_created"] += 1

        for rid in rids:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO record_entities(record_id, entity_id) "
                    "VALUES(?, ?)",
                    (rid, ent_id),
                )
                stats["links_created"] += 1
            except sqlite3.Error:
                pass

        if verbose:
            print(f"  '{place_name}' ← {len(rids)} photos "
                  f"({'Wiki' if wiki_name else 'GPS'})")

    conn.commit()
    return stats


# ───────────────────────────────────────────────────────────────────
# B4 Phase 3: time-series stories
# Group photos sharing a place_entity + a contiguous date span into
# `event` entities ("壱岐市 2026-04-15〜04-18 (37 枚)").
# ───────────────────────────────────────────────────────────────────


# Photos within this many seconds count as part of the same story.
# 48h tolerates a 1-day trip with a return flight or a mid-trip
# travel-rest day with no photos.
STORY_GAP_SEC = 48 * 3600

# A story needs at least this many photos to be worth its own entity.
STORY_MIN_PHOTOS = 4


def compute_time_stories(
    conn: sqlite3.Connection,
    min_photos: int = STORY_MIN_PHOTOS,
    gap_sec: int = STORY_GAP_SEC,
    verbose: bool = False,
) -> dict:
    """Group photos by place × contiguous date span → `event` entities."""
    init_kg_schema(conn)

    # Pull (record_id, timestamp, place_entity_id, place_name) for every
    # photos_app record that's already linked to a place via Phase 2.
    cur = conn.execute(
        """
        SELECT r.id, r.timestamp, e.id, e.name
        FROM records r
        JOIN record_entities re ON re.record_id = r.id
        JOIN entities e ON e.id = re.entity_id
        WHERE r.source = 'photos_app'
          AND e.type = 'place'
        ORDER BY e.id, r.timestamp
        """
    )
    rows = cur.fetchall()
    if not rows:
        if verbose:
            print("No photo→place links found. Run photos-place-clusters first.")
        return {"stories_created": 0, "links_created": 0}

    # Sweep through rows, breaking into stories whenever the place
    # changes or the time gap exceeds gap_sec.
    stats = {
        "stories_created": 0,
        "stories_reused": 0,
        "links_created": 0,
        "candidates_too_short": 0,
    }

    def _flush(story: list[tuple]) -> None:
        if len(story) < min_photos:
            stats["candidates_too_short"] += 1
            return
        place_name = story[0][3]
        first_ts = story[0][1]
        last_ts = story[-1][1]
        first_d = datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d")
        last_d = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d")
        if first_d == last_d:
            story_name = f"{place_name} {first_d}"
        else:
            story_name = f"{place_name} {first_d}〜{last_d}"

        before = conn.execute(
            "SELECT id FROM entities WHERE name = ?", (story_name,)
        ).fetchone()
        ent_id = upsert_entity(
            conn,
            name=story_name,
            type_="event",
            description=(
                f"{place_name} で撮影された写真 {len(story)} 枚 "
                f"({first_d}〜{last_d})"
            ),
        )
        if ent_id == 0:
            return
        if before:
            stats["stories_reused"] += 1
        else:
            stats["stories_created"] += 1
        for record_id, _, _, _ in story:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO record_entities(record_id, entity_id) "
                    "VALUES(?, ?)",
                    (record_id, ent_id),
                )
                stats["links_created"] += 1
            except sqlite3.Error:
                pass
        if verbose:
            print(f"  '{story_name}' ← {len(story)} photos")

    current: list[tuple] = []
    prev_place = None
    prev_ts = None
    for record_id, ts, place_id, place_name in rows:
        if (
            prev_place != place_id
            or (prev_ts is not None and ts - prev_ts > gap_sec)
        ):
            if current:
                _flush(current)
            current = []
        current.append((record_id, ts, place_id, place_name))
        prev_place = place_id
        prev_ts = ts
    if current:
        _flush(current)

    conn.commit()
    return stats
