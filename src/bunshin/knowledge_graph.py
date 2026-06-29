"""Knowledge graph: extract entities from records, build relations by co-occurrence.

Approach:
  1. Seed entity list from MEMORY.md (projects) + hardcoded knowns (orgs, places)
  2. Walk all records, link any record mentioning an entity name (or alias)
  3. Relations = co-occurrence count in same record
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL,           -- project / organization / person / place / topic
    aliases     TEXT,                    -- JSON array
    description TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS record_entities (
    record_id   TEXT NOT NULL,
    entity_id   INTEGER NOT NULL,
    PRIMARY KEY (record_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_re_entity ON record_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_re_record ON record_entities(record_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
"""


# Path for user-supplied entities (private, not committed)
USER_ENTITIES_PATH = Path.home() / ".bunshin" / "entities.json"

# Generic tech entities — safe to include in OSS code (no personal info)
GENERIC_ENTITIES = [
    {"name": "Claude Code", "type": "tool", "aliases": []},
    {"name": "Claude Desktop", "type": "tool", "aliases": []},
    {"name": "Ollama", "type": "tool", "aliases": []},
    {"name": "MCP", "type": "concept", "aliases": ["Model Context Protocol"]},
    {"name": "OpenAI", "type": "organization", "aliases": ["ChatGPT"]},
    {"name": "Anthropic", "type": "organization", "aliases": []},
    {"name": "Google", "type": "organization", "aliases": ["Gemini"]},
]


def load_user_entities() -> list[dict]:
    """Load user-supplied entities from ~/.bunshin/entities.json.

    Format: list of {"name": str, "type": str, "aliases": [str], "description": str}
    See README for example.
    """
    if not USER_ENTITIES_PATH.exists():
        return []
    try:
        data = json.loads(USER_ENTITIES_PATH.read_text())
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def init_kg_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def parse_projects_from_memory() -> list[dict]:
    """Read MEMORY.md and extract project entities."""
    # Reuse insights.py's auto-detection
    try:
        from bunshin.insights import find_memory_dir
        memory_dir = find_memory_dir()
    except Exception:
        memory_dir = None
    if not memory_dir:
        return []
    memory_path = memory_dir / "MEMORY.md"
    if not memory_path.exists():
        return []
    try:
        text = memory_path.read_text(encoding="utf-8")
    except OSError:
        return []
    projects = []
    for line in text.splitlines():
        m = re.match(r"^-\s+\[([^\]]+)\]\([^)]+\)\s*[—–\-]+\s*(.+)$", line.strip())
        if m:
            projects.append({
                "name": m.group(1).strip(),
                "type": "project",
                "description": m.group(2).strip(),
            })
    return projects


# Known-good entity-type mappings. LLM extractors routinely mislabel
# household names (e.g. YouTube as "place", note as "organization", etc).
# These overrides take precedence over whatever the LLM produced.
ENTITY_TYPE_OVERRIDES = {
    # Tech companies / services → organization
    "YouTube": "organization",
    "Google": "organization",
    "Apple": "organization",
    "Microsoft": "organization",
    "OpenAI": "organization",
    "Anthropic": "organization",
    "GitHub": "organization",
    "Twitter": "organization",
    "X": "organization",
    "LINE": "organization",
    "Facebook": "organization",
    "Instagram": "organization",
    "TikTok": "organization",
    "Spotify": "organization",
    "Suno": "organization",
    "Slack": "organization",
    "Notion": "organization",
    "Discord": "organization",
    "Zoom": "organization",
    "note": "organization",  # the JP blogging platform note.com
    "note inc.": "organization",
    "note inc": "organization",
    # Countries / regions / cities → place
    "日本": "place",
    "東京": "place",
    "京都": "place",
    "大阪": "place",
    "OSAKA": "place",
    "福岡": "place",
    "壱岐": "place",
    "壱岐島": "place",
    "壱岐市": "place",
    "長崎": "place",
    "沼津": "place",
    "ポーランド": "place",
    "韓国": "place",
    "中国": "place",
    "アメリカ": "place",
    "Poland": "place",
    "USA": "place",
    "Korea": "place",
    "Japan": "place",
    "Tokyo": "place",
    "Kyoto": "place",
    "Osaka": "place",
    "Fukuoka": "place",
    "Iki": "place",
    "Nagasaki": "place",
    "Numazu": "place",
    # Programming languages / tech → topic
    "Python": "topic",
    "JavaScript": "topic",
    "TypeScript": "topic",
    "Rust": "topic",
    "Go": "topic",
    "MCP": "topic",
    "AI": "topic",
    "LLM": "topic",
    "Ollama": "topic",
    "Claude": "topic",
    "ChatGPT": "topic",
    "GPT": "topic",
    # User-specific projects / publications → project
    # (Inferred from the user's MEMORY.md; safe defaults that get
    # individually validated downstream.)
    "ホークす": "project",
    "ホークす(海外帰りの模索日記)": "project",
    "MARINE FLIGHT": "organization",
    "AIR Flight": "organization",
    "reefballjapan": "organization",
    "リーフボールジャパン": "organization",
    "Reefball Japan": "organization",
}

# 🟡 竹 #6: pattern-based type inference for names the override dict
# doesn't list. LLM extractors often label company/handle names like
# "reefballjapan" or "marine_flight" as person; these patterns catch
# the obvious cases. Order matters — first match wins.
import re as _re

_TYPE_PATTERNS = [
    # Japanese corporate suffixes → organization
    (_re.compile(r"(株式会社|有限会社|合同会社|\(株\)|（株）)"), "organization"),
    # English corporate suffixes → organization
    (_re.compile(r"\b(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|GmbH|S\.A\.|N\.V\.)\b"), "organization"),
    # "-japan" / "-jp" / "japan-" handle/brand suffix → organization
    (_re.compile(r"(?i)(japan|jp)$"), "organization"),
    # Underscore_handles ('marine_flight', 'air_flight') → organization
    # (almost always a brand/account, never a person name)
    (_re.compile(r"^[a-z][a-z0-9_]+[a-z0-9]$"), "organization"),
]


def _pattern_type(name: str) -> str | None:
    """Return inferred type from name pattern, or None to leave to LLM."""
    if not name:
        return None
    for rx, t in _TYPE_PATTERNS:
        if rx.search(name):
            return t
    return None

# Entity names that are pure noise — single characters, very generic
# stop-words, fragments that the LLM extractor occasionally promotes.
# These get dropped at upsert time and pruned at startup.
NOISE_ENTITY_NAMES = {
    "the", "a", "an", "and", "or", "is", "are", "was", "were",
    "I", "you", "we", "they",
    "user", "assistant", "system",
    "TODO", "todo", "Note", "note?",  # ambiguous fragments
    "X1", "Y1", "test", "Test", "テスト",
    "?", "??", "...", "—",
}


def normalize_entity_type(name: str, default_type: str) -> str:
    """Return the canonical entity type for `name`, overriding the LLM's
    guess if we have a known-good mapping or a regex pattern hit."""
    if name in ENTITY_TYPE_OVERRIDES:
        return ENTITY_TYPE_OVERRIDES[name]
    pattern_t = _pattern_type(name)
    if pattern_t:
        return pattern_t
    return default_type


def apply_entity_type_overrides(conn: sqlite3.Connection) -> int:
    """Patch existing entities whose `type` disagrees with the override
    dict or matches a type-inference pattern. Returns rows updated.

    Called from app startup so old DBs heal themselves on the next launch.
    """
    fixed = 0
    # 1) Exact-match dictionary overrides.
    for name, canonical_type in ENTITY_TYPE_OVERRIDES.items():
        cur = conn.execute(
            "UPDATE entities SET type = ? WHERE name = ? AND type != ?",
            (canonical_type, name, canonical_type),
        )
        fixed += cur.rowcount
    # 2) Pattern-based inference for everything else.
    # Pull all entities once and check in Python — regex in SQL is
    # painful and the entity table is small (137 rows in Honda's DB).
    rows = conn.execute(
        "SELECT id, name, type, description FROM entities"
    ).fetchall()
    # v0.10.11 (Honda TOP2): description-based reclassify — catches
    # entities mis-classified by the extractor LLM when the describe
    # pass later wrote a clear "○○サイト" / "○○会社" body. e.g. before
    # this pass, X/Twitter / HackerNews / Reddit r/MachineLearning
    # were all `place` even though their AI descriptions read
    # "アメリカの会社が運営する…ソーシャルメディアサイト".
    _ORG_KEYWORDS = (
        "サイト", "ウェブサイト", "WEBサイト",
        "プラットフォーム",
        "会社", "企業", "Inc.", "Inc", "LLC", "Ltd",
        "コミュニティ", "掲示板", "フォーラム",
        "ソーシャルメディア", "SNS",
        "サブレディット", "Subreddit",
    )
    _GEO_KEYWORDS_IN_NAME = (
        "市", "町", "村", "区", "県", "府", "都", "島",
        "City", "County", "Town", "Village", "Prefecture", "Province",
    )
    for ent_id, name, current_type, description in rows:
        if name in ENTITY_TYPE_OVERRIDES:
            continue  # already handled above
        inferred = _pattern_type(name)
        if inferred and inferred != current_type:
            conn.execute(
                "UPDATE entities SET type = ? WHERE id = ?",
                (inferred, ent_id),
            )
            fixed += 1
            continue
        # description-based reclassify (only for already-existing
        # descriptions). place → organization if body talks about it
        # as a site/company/platform AND name has no geographic suffix.
        if (
            current_type == "place"
            and description
            and any(kw in description for kw in _ORG_KEYWORDS)
            and not any(g in name for g in _GEO_KEYWORDS_IN_NAME)
        ):
            conn.execute(
                "UPDATE entities SET type = 'organization' WHERE id = ?",
                (ent_id,),
            )
            fixed += 1
    if fixed:
        conn.commit()
    return fixed


def upsert_entity(
    conn: sqlite3.Connection,
    name: str,
    type_: str,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> int:
    # Drop noise immediately. Returning 0 is a sentinel "not stored"
    # that callers can check before inserting record_entities links.
    if name in NOISE_ENTITY_NAMES or len(name.strip()) < 2:
        return 0
    # Always normalize the type against our override dict — LLM-extracted
    # types are noisy and we can do better with a curated list.
    type_ = normalize_entity_type(name, type_)
    cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        # If the existing row has the wrong type, fix it.
        conn.execute("UPDATE entities SET type = ? WHERE id = ? AND type != ?",
                     (type_, row[0], type_))
        return row[0]
    cursor = conn.execute(
        """INSERT INTO entities(name, type, aliases, description, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            name,
            type_,
            json.dumps(aliases or [], ensure_ascii=False),
            description,
            int(datetime.now().timestamp()),
        ),
    )
    return cursor.lastrowid


def seed_entities(conn: sqlite3.Connection) -> dict:
    """Seed entities from three sources:
      1. MEMORY.md projects (auto-detected)
      2. ~/.bunshin/entities.json (user-supplied, private)
      3. Built-in generic tech entities (Claude/Ollama/MCP etc.)
    """
    init_kg_schema(conn)
    stats = {
        "seeded": 0,
        "from_memory": 0,
        "from_user_config": 0,
        "from_generic": 0,
    }

    for p in parse_projects_from_memory():
        upsert_entity(conn, p["name"], "project", description=p.get("description"))
        stats["from_memory"] += 1
        stats["seeded"] += 1

    for e in load_user_entities():
        upsert_entity(
            conn, e["name"], e.get("type", "topic"),
            aliases=e.get("aliases", []),
            description=e.get("description"),
        )
        stats["from_user_config"] += 1
        stats["seeded"] += 1

    for e in GENERIC_ENTITIES:
        upsert_entity(
            conn, e["name"], e["type"],
            aliases=e.get("aliases", []),
            description=e.get("description"),
        )
        stats["from_generic"] += 1
        stats["seeded"] += 1

    conn.commit()
    return stats


def get_all_entities(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        "SELECT id, name, type, aliases, description FROM entities ORDER BY name"
    )
    return [
        {
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "aliases": json.loads(r[3]) if r[3] else [],
            "description": r[4],
        }
        for r in cursor.fetchall()
    ]


def link_records_to_entities(
    conn: sqlite3.Connection,
    batch_size: int = 200,
    verbose: bool = False,
) -> dict:
    """Walk all records, link any that mention a known entity (or alias)."""
    init_kg_schema(conn)
    stats = {"records_scanned": 0, "links_inserted": 0, "entities_used": 0}

    entities = get_all_entities(conn)
    # name → entity_id map (include aliases)
    name_to_id: dict[str, int] = {}
    for e in entities:
        name_to_id[e["name"]] = e["id"]
        for alias in e["aliases"]:
            if alias and alias not in name_to_id:
                name_to_id[alias] = e["id"]

    if not name_to_id:
        stats["error"] = "No entities seeded"
        return stats

    # Sort longest first → greedy match (avoid substring collisions)
    names_sorted = sorted(name_to_id.keys(), key=lambda n: -len(n))

    # Wipe old links first (idempotent rebuild)
    conn.execute("DELETE FROM record_entities")
    conn.commit()

    used_entities = set()
    cursor = conn.execute("SELECT id, content FROM records WHERE content IS NOT NULL")

    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        for record_id, content in batch:
            stats["records_scanned"] += 1
            mentioned_ids = set()
            for name in names_sorted:
                if name in content:
                    mentioned_ids.add(name_to_id[name])
            for entity_id in mentioned_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO record_entities(record_id, entity_id) VALUES (?, ?)",
                    (record_id, entity_id),
                )
                stats["links_inserted"] += 1
                used_entities.add(entity_id)
        conn.commit()
        if verbose:
            print(f"  scanned {stats['records_scanned']}")

    stats["entities_used"] = len(used_entities)
    return stats


def entity_with_counts(conn: sqlite3.Connection) -> list[dict]:
    """Return all entities with their mention count, sorted desc."""
    cursor = conn.execute(
        """SELECT e.id, e.name, e.type, e.description,
                  COUNT(re.record_id) as mentions
           FROM entities e
           LEFT JOIN record_entities re ON re.entity_id = e.id
           GROUP BY e.id
           ORDER BY mentions DESC, e.name"""
    )
    return [
        {
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "description": r[3],
            "mentions": r[4],
        }
        for r in cursor.fetchall()
    ]


def get_top_entities(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    type_: str | None = None,
    with_sources: bool = False,
    exclude_noisy: bool = False,
) -> list[dict]:
    """Single source of truth for "most-mentioned entities" lookups —
    used by both the HTTP /api/entities endpoint and the MCP
    list_top_entities tool, so external AI agents always see the same
    list the web UI shows.

    Args:
        limit: cap on number of entities returned (post-filter).
        type_: optional type filter ("person" / "project" / etc).
        with_sources: attach `top_sources` (per-source mention breakdown).
        exclude_noisy: drop entities whose mentions are >80% gmail/browser
            (newsletter-driven noise like "note", "ポーランド").
    """
    all_entities = entity_with_counts(conn)
    if type_:
        all_entities = [e for e in all_entities if e.get("type") == type_]
    # Overfetch when we'll filter by source share so we still hit `limit`
    # after dropping noise.
    pool = all_entities[: limit * 3 if exclude_noisy else limit]
    out: list[dict] = []
    for e in pool:
        if len(out) >= limit:
            break
        eid = e.get("id")
        src_breakdown: dict[str, int] = {}
        if eid is not None and (with_sources or exclude_noisy):
            src_rows = conn.execute(
                "SELECT r.source, COUNT(*) FROM record_entities re "
                "JOIN records r ON r.id = re.record_id "
                "WHERE re.entity_id = ? GROUP BY r.source "
                "ORDER BY 2 DESC",
                (eid,),
            ).fetchall()
            src_breakdown = {row[0]: row[1] for row in src_rows}
        if exclude_noisy and src_breakdown:
            total = sum(src_breakdown.values()) or 1
            noise = (src_breakdown.get("gmail", 0) +
                     src_breakdown.get("browser", 0)) / total
            if noise > 0.8:
                continue
        entry = dict(e)
        if with_sources:
            entry["top_sources"] = src_breakdown
        out.append(entry)
    return out


def entity_relations(
    conn: sqlite3.Connection,
    entity_id: int,
    limit: int = 20,
) -> list[dict]:
    """Find related entities with co-occurrence + specificity + density scores.

    Returns each relation with:
      - weight: density-weighted co-occurrence over distinct sessions.
        Each session contributes 1 / sqrt(N) where N is the number of
        DISTINCT entities in that session — so a deep-research session
        that name-drops 50 different AI orgs contributes ~0.14 per pair,
        while a small focused session with just 2-3 entities contributes
        ~0.7. Without this, a single dj-engine deep-research session
        was pushing "Sequoia" / "X/Twitter" / "a16z" to the top of
        壱岐島's relations (Reviewer-Honda 14 + reviewer 22).
      - sessions: raw count of DISTINCT sessions where they co-occur
        (kept for display — "5 sessions together")
      - e2_total: total SESSIONS where the related entity appears
      - specificity: weight / sqrt(e2_total) — log-style decay so a
        globally-popular entity doesn't dominate just by being popular,
        but isn't punished as harshly as the prior linear divisor
      - type_match_bonus: 1.0 if both entities are same type, 0.85 if
        different. Soft penalty for cross-domain noise (壱岐島=place,
        a16z=organization) without zeroing it out (sometimes cross-
        domain IS the interesting story).
      - score: weight × specificity × type_match_bonus, sorted DESC.
    """
    # Pre-compute the center entity's type so we can apply the
    # cross-type penalty in the SELECT.
    cur_type = conn.execute(
        "SELECT type FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    center_type = (cur_type[0] if cur_type else None) or ""

    cursor = conn.execute(
        """WITH session_density AS (
              SELECT r.source_id, COUNT(DISTINCT re.entity_id) AS n
                FROM records r
                JOIN record_entities re ON re.record_id = r.id
               WHERE r.source_id IS NOT NULL
               GROUP BY r.source_id
           ),
           e2_totals AS (
              SELECT re_x.entity_id, COUNT(DISTINCT r.source_id) AS total
                FROM record_entities re_x
                JOIN records r ON r.id = re_x.record_id
               WHERE r.source_id IS NOT NULL
               GROUP BY re_x.entity_id
           )
           SELECT e2.id, e2.name, e2.type,
                  SUM(1.0 / SQRT(MAX(sd.n, 1))) AS weighted,
                  COUNT(DISTINCT r1.source_id) AS sessions,
                  COALESCE(e2t.total, 1) AS e2_total
             FROM record_entities re1
             JOIN records r1 ON r1.id = re1.record_id
             JOIN record_entities re2
               ON re2.record_id = re1.record_id
               AND re2.entity_id != re1.entity_id
             JOIN entities e2 ON e2.id = re2.entity_id
             JOIN session_density sd ON sd.source_id = r1.source_id
             LEFT JOIN e2_totals e2t ON e2t.entity_id = e2.id
            WHERE re1.entity_id = ?
              AND r1.source_id IS NOT NULL
            GROUP BY e2.id""",
        (entity_id,),
    )
    relations = []
    for r in cursor.fetchall():
        weighted = float(r[3] or 0)
        sessions = int(r[4] or 0)
        e2_total = max(int(r[5] or 1), 1)
        # sqrt-decay specificity — less harsh than weight/e2_total,
        # so "壱岐島 ↔ ドローン" (mid e2_total) isn't drowned by ultra-
        # rare niche pairs.
        specificity = weighted / (e2_total ** 0.5)
        e2_type = r[2] or ""
        type_match_bonus = 1.0 if (center_type and e2_type == center_type) else 0.85
        score = weighted * specificity * type_match_bonus
        relations.append({
            "id": r[0],
            "name": r[1],
            "type": e2_type,
            # `weight` kept as session count for backwards-compat
            # rendering; downstream UI shows "5 回共起" or similar.
            "weight": sessions,
            "weighted_density": round(weighted, 3),
            "e2_total": e2_total,
            "specificity": round(specificity, 3),
            "type_match_bonus": type_match_bonus,
            "score": round(score, 3),
        })
    relations.sort(key=lambda x: -x["score"])
    return relations[:limit]


def entity_records(
    conn: sqlite3.Connection,
    entity_id: int,
    limit: int = 20,
) -> list[dict]:
    """Recent records mentioning this entity."""
    cursor = conn.execute(
        """SELECT r.id, r.source, r.source_id, r.content, r.timestamp, r.metadata
           FROM record_entities re
           JOIN records r ON r.id = re.record_id
           WHERE re.entity_id = ?
           ORDER BY r.timestamp DESC
           LIMIT ?""",
        (entity_id, limit),
    )
    out = []
    for r in cursor.fetchall():
        meta = json.loads(r[5]) if r[5] else None
        out.append({
            "id": r[0],
            "source": r[1],
            "source_id": r[2],
            "content": r[3],
            "timestamp": r[4],
            "metadata": meta,
        })
    return out


def entity_by_id(conn: sqlite3.Connection, entity_id: int) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT e.id, e.name, e.type, e.aliases, e.description, "
        "       COUNT(re.record_id) AS mentions "
        "FROM entities e LEFT JOIN record_entities re ON re.entity_id = e.id "
        "WHERE e.id = ? GROUP BY e.id",
        (entity_id,),
    )
    r = cursor.fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "name": r[1],
        "type": r[2],
        "aliases": json.loads(r[3]) if r[3] else [],
        "description": r[4],
        "mentions": r[5] or 0,
        "mention_count": r[5] or 0,  # alias for compatibility with MCP callers
    }


def add_custom_entity(
    conn: sqlite3.Connection,
    name: str,
    type_: str = "topic",
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> int:
    """Manually add an entity (e.g., person name discovered later)."""
    init_kg_schema(conn)
    return upsert_entity(conn, name, type_, aliases=aliases, description=description)


# ────────────────────────────────────────────────────────────
# LLM-based entity discovery
# ────────────────────────────────────────────────────────────

_DISCOVERY_PROMPT = """以下のテキストから、実際に登場する**人物名・組織名・プロジェクト名・場所名**を抽出してください。

ルール：
- テキスト中に**明示的に名前として登場するもののみ**抽出（推測しない）
- 一般名詞（「会社」「人」「ドローン」など）は抽出しない
- 重複は除く
- JSON のみで応答（説明文・コードブロック禁止）

出力フォーマット：
{"entities": [{"name": "...", "type": "person|organization|project|place"}]}

抽出対象テキスト：
"""


# Names we want to exclude from auto-discovery (case-insensitive substring or exact).
# These tend to surface from Claude/AI internal artifacts or are too generic to be useful.
_ENTITY_NOISE_EXACT = {
    "todowrite", "askuserquestion", "taskcreate", "taskupdate",
    "read", "write", "edit", "bash", "grep", "glob",
    "user", "assistant", "system", "claude",
    "none", "null", "n/a",
}
_ENTITY_NOISE_GENERIC = {
    "ドローン会社", "会社", "プロジェクト", "事業",
    "メール", "ファイル",
}


def _is_noise_entity(name: str) -> bool:
    """Skip single-letter labels, AI tool names, and overly generic nouns."""
    s = name.strip()
    if not s:
        return True
    # Single-letter or 2-character ASCII (option enumerators like "A", "F")
    if len(s) <= 2 and all(c.isascii() and c.isalpha() for c in s):
        return True
    # Pure ASCII 3 chars or fewer, all letters → likely garbage (tool names tend to fit)
    if len(s) <= 3 and all(c.isascii() and (c.isalnum() or c in "._-") for c in s):
        return True
    if s.lower() in _ENTITY_NOISE_EXACT:
        return True
    if s in _ENTITY_NOISE_GENERIC:
        return True
    # Looks like a Claude tool invocation marker
    if s.startswith("tool_use") or "[tool_" in s:
        return True
    return False


def _parse_llm_entity_response(text: str) -> list[dict]:
    """Parse Ollama response. Tolerates code fences and stray prose around the JSON."""
    import re
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    match = re.search(r"\{[\s\S]*\}", s)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        ents = data.get("entities", []) if isinstance(data, dict) else []
        out = []
        for e in ents:
            if not isinstance(e, dict):
                continue
            name = (e.get("name") or "").strip()
            type_ = (e.get("type") or "topic").strip().lower()
            if not name or type_ not in {"person", "organization", "project", "place", "tool", "concept"}:
                continue
            if _is_noise_entity(name):
                continue
            out.append({"name": name, "type": type_})
        return out
    except json.JSONDecodeError:
        return []


def cleanup_noise_entities(conn: sqlite3.Connection) -> int:
    """Remove obvious noise entities that may have been added before filters existed."""
    init_kg_schema(conn)
    cursor = conn.execute("SELECT id, name FROM entities")
    to_delete = [eid for eid, name in cursor.fetchall() if _is_noise_entity(name)]
    if not to_delete:
        return 0
    placeholders = ",".join(["?"] * len(to_delete))
    conn.execute(f"DELETE FROM record_entities WHERE entity_id IN ({placeholders})", to_delete)
    conn.execute(f"DELETE FROM entities WHERE id IN ({placeholders})", to_delete)
    conn.commit()
    return len(to_delete)


def discover_entities_via_llm(
    conn: sqlite3.Connection,
    sample_size: int = 100,
    model: Optional[str] = None,
    min_content_length: int = 200,
    progress_callback=None,
) -> dict:
    """Use Ollama to discover new entities mentioned in records.

    Samples records (favoring high-information sources: claude turns,
    long files, recent gmail), asks the LLM to extract named entities,
    dedupes against existing, and inserts new ones.

    Skips entities already known under any of their (name + aliases).
    """
    init_kg_schema(conn)
    stats = {"records_processed": 0, "entities_found": 0, "entities_new": 0, "errors": 0}

    try:
        from bunshin.chat import OLLAMA_HOST, check_ollama, pick_model
        import httpx
    except ImportError:
        stats["error"] = "Required modules missing"
        return stats

    ok, available = check_ollama()
    if not ok or not available:
        stats["error"] = "Ollama not available"
        return stats

    chosen = model or pick_model(available)
    stats["model"] = chosen

    # Build the known-name set (lowercased) so we can dedupe quickly.
    known_lc: set[str] = set()
    for e in get_all_entities(conn):
        known_lc.add(e["name"].lower())
        for alias in e["aliases"]:
            if alias:
                known_lc.add(alias.lower())

    # Pull a sample of high-value records.
    cursor = conn.execute(
        """SELECT content FROM records
           WHERE content IS NOT NULL
             AND length(content) >= ?
             AND source IN ('claude', 'file', 'gmail')
           ORDER BY RANDOM()
           LIMIT ?""",
        (min_content_length, sample_size),
    )
    samples = [row[0] for row in cursor.fetchall()]

    discovered: dict[str, str] = {}  # name → type

    for i, content in enumerate(samples):
        # Truncate to avoid huge prompts
        snippet = content[:2500]
        payload = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": _DISCOVERY_PROMPT + snippet},
            ],
            "stream": False,
            "format": "json",
        }
        try:
            r = httpx.post(
                f"{OLLAMA_HOST}/api/chat", json=payload, timeout=90.0
            )
            r.raise_for_status()
            response_text = r.json().get("message", {}).get("content", "")
            ents = _parse_llm_entity_response(response_text)
            for e in ents:
                name = e["name"]
                if name.lower() in known_lc:
                    continue
                if name not in discovered:
                    discovered[name] = e["type"]
            stats["records_processed"] += 1
        except Exception:
            stats["errors"] += 1

        if progress_callback:
            progress_callback(i + 1, len(samples), len(discovered))

    stats["entities_found"] = len(discovered)

    # Insert discovered ones
    for name, type_ in discovered.items():
        try:
            upsert_entity(conn, name, type_, description="(LLM 抽出)")
            stats["entities_new"] += 1
        except Exception:
            pass

    conn.commit()
    return stats
