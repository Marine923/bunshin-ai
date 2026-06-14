"""Tests for bunshin.knowledge_graph entity linking and relations."""
from bunshin.knowledge_graph import (
    GENERIC_ENTITIES,
    add_custom_entity,
    entity_relations,
    entity_with_counts,
    init_kg_schema,
    link_records_to_entities,
    upsert_entity,
)


def test_init_kg_schema_creates_tables(conn):
    init_kg_schema(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('entities', 'record_entities')"
    )
    tables = {row[0] for row in cursor.fetchall()}
    assert "entities" in tables
    assert "record_entities" in tables


def test_upsert_entity_idempotent(conn):
    init_kg_schema(conn)
    e1 = upsert_entity(conn, "TestProject", "project", ["TP"], "A test project")
    e2 = upsert_entity(conn, "TestProject", "project", ["TP"], "A test project")
    assert e1 == e2  # same ID returned


def test_generic_entities_well_formed():
    for e in GENERIC_ENTITIES:
        assert "name" in e
        assert "type" in e
        assert e["type"] in {"organization", "person", "place", "project", "tool", "concept", "topic"}


def test_link_records_finds_entity_in_content(populated_conn):
    init_kg_schema(populated_conn)
    # Add an entity for Sky MISSION which appears in our fixture
    upsert_entity(populated_conn, "Sky MISSION", "organization", ["スカイミッション"])
    upsert_entity(populated_conn, "壱岐黄金プロジェクト", "project")

    stats = link_records_to_entities(populated_conn)
    assert stats["records_scanned"] >= 5
    assert stats["links_inserted"] >= 2  # Sky MISSION + 壱岐黄金プロジェクト at minimum


def test_entity_with_counts_returns_mentions(populated_conn):
    init_kg_schema(populated_conn)
    upsert_entity(populated_conn, "Sky MISSION", "organization")
    upsert_entity(populated_conn, "壱岐黄金プロジェクト", "project")
    link_records_to_entities(populated_conn)

    entities = entity_with_counts(populated_conn)
    by_name = {e["name"]: e for e in entities}
    assert by_name["Sky MISSION"]["mentions"] >= 1
    assert by_name["壱岐黄金プロジェクト"]["mentions"] >= 1


def test_entity_relations_specificity_calculation(populated_conn):
    init_kg_schema(populated_conn)
    upsert_entity(populated_conn, "Sky MISSION", "organization")
    link_records_to_entities(populated_conn)
    entities = entity_with_counts(populated_conn)
    sky_id = next(e["id"] for e in entities if e["name"] == "Sky MISSION")
    rels = entity_relations(populated_conn, sky_id)
    # Specificity is bounded
    for r in rels:
        assert 0 <= r["specificity"] <= 1
        assert r["weight"] >= 1
