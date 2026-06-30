"""Regression tests for v0.10.18-19 entity-hygiene CLIs and v0.10.28+ pin-context.

These tests don't exercise the CLI runner directly — they validate the
underlying SQL invariants that merge-entities, find-duplicates, and the
pin mechanism rely on. If any of these breaks, the user-facing
workflow (`bunshin doctor` → `bunshin photos-relabel-places` →
`bunshin find-duplicates` → `bunshin merge-entities`) silently
corrupts state.
"""
import sqlite3

import pytest

from bunshin.storage import init_db


def _seed_entities(conn: sqlite3.Connection, rows):
    """rows: [(name, type, description), ...] — returns inserted IDs."""
    ids = []
    for name, type_, desc in rows:
        cur = conn.execute(
            "INSERT INTO entities (name, type, description, created_at) "
            "VALUES (?, ?, ?, strftime('%s','now'))",
            (name, type_, desc),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _link(conn, record_id, entity_id):
    conn.execute(
        "INSERT OR IGNORE INTO record_entities (record_id, entity_id) VALUES (?, ?)",
        (record_id, entity_id),
    )


def test_merge_collapses_record_entities_with_unique_constraint(populated_conn):
    """When source and target both point at the same record, the merge must
    DELETE the source link first (UNIQUE(record_id, entity_id) would otherwise
    crash). This is the exact pattern the merge-entities CLI relies on."""
    conn = populated_conn
    # Ensure KG tables exist
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    src_id, tgt_id = _seed_entities(conn, [
        ("ホークす(海外帰り)", "project", None),
        ("ホークす", "project", None),
    ])
    # Both entities link to records 1 and 2 (overlap = conflict)
    for rid in (1, 2):
        _link(conn, rid, src_id)
        _link(conn, rid, tgt_id)
    # Source-only link to record 3 (should survive as a rewrite)
    _link(conn, 3, src_id)
    conn.commit()

    # Apply the merge SQL the CLI runs:
    with conn:
        conn.execute(
            "DELETE FROM record_entities "
            "WHERE entity_id = ? "
            "AND EXISTS (SELECT 1 FROM record_entities re2 "
            "            WHERE re2.entity_id = ? AND re2.record_id = record_entities.record_id)",
            (src_id, tgt_id),
        )
        conn.execute(
            "UPDATE record_entities SET entity_id = ? WHERE entity_id = ?",
            (tgt_id, src_id),
        )
        conn.execute("DELETE FROM entities WHERE id = ?", (src_id,))

    # Source entity must be gone
    assert conn.execute(
        "SELECT COUNT(*) FROM entities WHERE id = ?", (src_id,)
    ).fetchone()[0] == 0

    # Target must own records 1, 2, AND 3 (3 was the rewritten one).
    # record_id can be either INTEGER or TEXT depending on the column
    # affinity from records — normalize to str for comparison.
    tgt_records = {
        str(r[0]) for r in conn.execute(
            "SELECT record_id FROM record_entities WHERE entity_id = ?",
            (tgt_id,),
        )
    }
    assert tgt_records == {"1", "2", "3"}

    # No dangling source rows
    assert conn.execute(
        "SELECT COUNT(*) FROM record_entities WHERE entity_id = ?", (src_id,)
    ).fetchone()[0] == 0


def test_find_duplicates_normalize_collapses_parens_and_punctuation():
    """The CLI normalizes name by stripping parenthesized suffixes,
    whitespace, lowercase, and a few punctuation marks. Two entities
    that differ only by these should hash to the same key."""
    import re as _re

    def _normalize(name: str) -> str:
        if not name:
            return ""
        s = _re.sub(r"\s*[（(].*?[)）]\s*", "", name)
        s = s.strip().lower()
        return _re.sub(r"[ \t/・,，、:：·]", "", s)

    # Real cases from Honda's DB
    assert _normalize("ホークす(海外帰りの模索日記)") == _normalize("ホークす")
    assert _normalize("MARINE FLIGHT（主催ブランド名）") == _normalize("MARINE FLIGHT")
    assert _normalize("MARINE FLIGHT") == _normalize("marine flight")
    assert _normalize("MARINE FLIGHT") == _normalize("MARINE・FLIGHT")
    # Stay-different cases
    assert _normalize("壱岐市") != _normalize("壱岐島")
    # Hyphen is intentionally preserved (it's part of names like
    # "Cloud-Flare" or model strings, not punctuation noise)
    assert _normalize("Coca-Cola") != _normalize("Cocacola")


def test_pin_setting_set_get_clear_via_settings_table(conn):
    """The pin-context CLI / UI / MCP all write to the same settings
    row under `pin:entity:<id>`. Verify the round-trip."""
    from bunshin.settings import get as get_setting

    # Set
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("pin:entity:42", "壱岐黄金プロジェクト・MARINE FLIGHT・海洋教育の活動拠点"),
        )
    assert "壱岐黄金" in (get_setting(conn, "pin:entity:42") or "")

    # Overwrite
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("pin:entity:42", "updated"),
        )
    assert get_setting(conn, "pin:entity:42") == "updated"

    # Clear
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", ("pin:entity:42",))
    assert (get_setting(conn, "pin:entity:42") or "") == ""


def test_apply_entity_type_overrides_tool_keywords(conn):
    """v0.10.28-29: Deck A / Deck B were misclassified as `place`
    because their descriptions read "DJソフトウェア内の機能" /
    "ミックス機能". Verify the reclassify rule catches them."""
    from bunshin.knowledge_graph import apply_entity_type_overrides, init_kg_schema
    init_kg_schema(conn)

    deck_a, deck_b, real_place = _seed_entities(conn, [
        ("Deck A", "place",
         "これはDJソフトウェア内の機能です。曲をロードして再生します。"),
        ("Deck B", "place",
         "音楽ミックスやパフォーマンスに使用されるソフトウェア機能です。"),
        ("諫早市", "place", "長崎県諫早市。本田の生活圏。"),
    ])
    n = apply_entity_type_overrides(conn)
    assert n >= 2  # Deck A + Deck B should both flip

    rows = {
        r[0]: r[1] for r in conn.execute(
            "SELECT id, type FROM entities WHERE id IN (?, ?, ?)",
            (deck_a, deck_b, real_place),
        )
    }
    assert rows[deck_a] == "tool", f"Deck A should be tool, got {rows[deck_a]}"
    assert rows[deck_b] == "tool", f"Deck B should be tool, got {rows[deck_b]}"
    # Real place must NOT be touched (no tool/org/concept keywords in desc)
    assert rows[real_place] == "place"
