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


def upsert_entity(
    conn: sqlite3.Connection,
    name: str,
    type_: str,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> int:
    cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
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


def entity_relations(
    conn: sqlite3.Connection,
    entity_id: int,
    limit: int = 20,
) -> list[dict]:
    """Find related entities with both co-occurrence and specificity scores.

    Returns each relation with:
      - weight: raw co-occurrence count
      - e2_total: total mentions of the related entity (denominator)
      - specificity: weight / e2_total (0..1, how much of this entity is dedicated to ours)
      - score: hybrid score for ranking = weight * sqrt(specificity)

    Sorted by score DESC so we get strong AND specific relations first,
    avoiding the "everything-co-occurs-with-globally-frequent-entity" problem.
    """
    cursor = conn.execute(
        """SELECT e2.id, e2.name, e2.type,
                  COUNT(*) AS weight,
                  (SELECT COUNT(*) FROM record_entities
                   WHERE entity_id = e2.id) AS e2_total
           FROM record_entities re1
           JOIN record_entities re2
             ON re1.record_id = re2.record_id
             AND re1.entity_id != re2.entity_id
           JOIN entities e2 ON e2.id = re2.entity_id
           WHERE re1.entity_id = ?
           GROUP BY e2.id""",
        (entity_id,),
    )
    relations = []
    for r in cursor.fetchall():
        weight = r[3]
        e2_total = max(r[4] or 1, 1)
        specificity = weight / e2_total
        score = weight * (specificity ** 0.5)
        relations.append({
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "weight": weight,
            "e2_total": e2_total,
            "specificity": round(specificity, 3),
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
        "SELECT id, name, type, aliases, description FROM entities WHERE id = ?",
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
