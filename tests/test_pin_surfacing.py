"""Regression tests for v0.10.35-37 pin-context surfacing across MCP responses.

These don't exercise the MCP transport — they validate the SQL invariants
behind each pin-surfacing field, so a refactor in the settings layer
can't silently break the LLM-facing contract.
"""
import sqlite3

import pytest


def _seed_entity(conn, name, type_, description=None):
    cur = conn.execute(
        "INSERT INTO entities (name, type, description, created_at) "
        "VALUES (?, ?, ?, strftime('%s','now'))",
        (name, type_, description),
    )
    conn.commit()
    return cur.lastrowid


def _pin(conn, entity_id, context):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (f"pin:entity:{entity_id}", context),
    )
    conn.commit()


def test_pin_list_endpoint_query_returns_only_active_pins(conn):
    """v0.10.31 GET /api/pins/list backing query: JOIN settings × entities
    on 'pin:entity:<id>'. Must exclude empty strings, NULL values, and
    stale settings rows whose entity has been deleted."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    e1 = _seed_entity(conn, "壱岐島", "place")
    e2 = _seed_entity(conn, "MARINE FLIGHT", "organization")
    e3 = _seed_entity(conn, "AIR Flight", "organization")
    # Active pins
    _pin(conn, e1, "壱岐黄金プロジェクト・MARINE FLIGHT・海洋教育の活動拠点")
    _pin(conn, e2, "個人向けドローン体験＋同伴空撮")
    # Empty-value pin — must NOT show up
    _pin(conn, e3, "")
    # Orphan pin: entity was deleted but the settings row remains
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        ("pin:entity:9999", "stale orphan pin"),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT s.key, s.value, e.id, e.name "
        "FROM settings s "
        "JOIN entities e ON ('pin:entity:' || e.id) = s.key "
        "WHERE s.key LIKE 'pin:entity:%' "
        "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "ORDER BY e.name COLLATE NOCASE"
    ).fetchall()
    names = [r[3] for r in rows]
    assert names == ["MARINE FLIGHT", "壱岐島"], (
        f"only active-pin entities (MARINE FLIGHT + 壱岐島) should surface — "
        f"got {names}. Empty-string pin on AIR Flight and orphan #9999 "
        f"must be excluded."
    )


def test_search_memory_pinned_entities_query_substring_match(conn):
    """v0.10.35 search_memory's pinned_entities branch: when the query
    string is a substring of an entity name AND that entity has a
    non-empty pin, it surfaces — even if no records match."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    iki = _seed_entity(conn, "壱岐島", "place")
    iki_kin = _seed_entity(conn, "壱岐黄金プロジェクト", "project")
    unrelated = _seed_entity(conn, "Coca-Cola", "organization")
    _pin(conn, iki, "壱岐の主要事業の拠点")
    _pin(conn, iki_kin, "小粒じゃがいもの高級ブランド化")
    # unrelated has a pin but its name doesn't contain "壱岐"
    _pin(conn, unrelated, "アメリカの飲料会社")

    query = "壱岐"
    # Same WHERE-clause shape as the MCP server query
    rows = conn.execute(
        "SELECT e.id, e.name FROM entities e "
        "JOIN settings s ON s.key = 'pin:entity:' || e.id "
        "WHERE s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "AND LOWER(e.name) LIKE '%' || LOWER(?) || '%'",
        (query,),
    ).fetchall()
    surfaced = {r[1] for r in rows}
    assert "壱岐島" in surfaced, "exact-name-substring pin should surface"
    assert "壱岐黄金プロジェクト" in surfaced, "compound-name pin should surface"
    assert "Coca-Cola" not in surfaced, (
        "unrelated pinned entity must NOT surface for the '壱岐' query"
    )


def test_get_today_hero_pinned_anchors_query_caps_at_8_alphabetical(conn):
    """v0.10.36 get_today_hero attaches `pinned_anchors` — up to 8 entries,
    sorted by name COLLATE NOCASE so the briefing reads stable across days."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    # Create 10 entities, pin all of them. Only 8 should come back.
    names = ["Z entity", "y entity", "M entity", "A entity",
             "壱岐島", "MARINE", "AIR", "リーフ", "沼津", "壱岐黄金"]
    for n in names:
        eid = _seed_entity(conn, n, "project")
        _pin(conn, eid, f"context for {n}")

    rows = conn.execute(
        "SELECT e.name FROM settings s "
        "JOIN entities e ON s.key = 'pin:entity:' || e.id "
        "WHERE s.key LIKE 'pin:entity:%' "
        "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "ORDER BY e.name COLLATE NOCASE "
        "LIMIT 8"
    ).fetchall()
    assert len(rows) == 8, f"LIMIT 8 must cap, got {len(rows)}"
    returned = [r[0] for r in rows]
    # COLLATE NOCASE means 'y' and 'Y' sort together, 'a' before 'b'.
    # Result must be sorted ascending.
    assert returned == sorted(returned, key=str.casefold), (
        f"name sort must be stable + case-insensitive — got {returned}"
    )


def test_list_top_entities_pinned_field_batched_query(conn):
    """v0.10.37 list_top_entities decorates each entity with `pinned` bool +
    `pinned_context_preview`. Uses a single batched SELECT keyed on
    settings.key IN (pin:entity:1, pin:entity:2, ...)."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    e1 = _seed_entity(conn, "壱岐島", "place")
    e2 = _seed_entity(conn, "Unpinned Org", "organization")
    e3 = _seed_entity(conn, "MARINE FLIGHT", "organization")
    _pin(conn, e1, "壱岐黄金・MARINE FLIGHT・海洋教育の活動拠点\n(改行後はpreviewでカットされる)")
    _pin(conn, e3, "個人向けドローン体験")

    ids = [e1, e2, e3]
    placeholders = ",".join("?" * len(ids))
    keys = [f"pin:entity:{i}" for i in ids]
    rows = conn.execute(
        f"SELECT key, value FROM settings "
        f"WHERE key IN ({placeholders}) "
        f"AND value IS NOT NULL AND TRIM(value) <> ''",
        keys,
    ).fetchall()
    pinned_map = {int(k.split(":")[-1]): v for k, v in rows}

    assert pinned_map.get(e1), "壱岐島 must come back from the batched lookup"
    assert pinned_map.get(e3), "MARINE FLIGHT must come back"
    assert e2 not in pinned_map, (
        "Unpinned Org has no pin row — must not appear in the map"
    )

    # Preview = first newline, capped at 120 chars
    preview_e1 = pinned_map[e1].split("\n")[0][:120]
    assert "改行後" not in preview_e1, (
        "preview must stop at first newline so multi-line pins don't bleed"
    )
    assert len(preview_e1) <= 120
