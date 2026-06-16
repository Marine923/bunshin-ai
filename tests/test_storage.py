"""Tests for bunshin.storage."""
import sqlite3

from bunshin.storage import (
    count_records,
    count_short_records,
    delete_short_records,
    get_session_records,
    init_db,
    insert_record,
    list_sources_with_counts,
)


def test_init_db_idempotent(tmp_db_path):
    """init_db can be called multiple times without errors."""
    c1 = init_db(tmp_db_path)
    c1.close()
    c2 = init_db(tmp_db_path)
    c2.close()
    assert tmp_db_path.exists()


def test_insert_record_returns_id(conn):
    rid = insert_record(
        conn, source="manual", timestamp=1717800000,
        content="hello world this is a test memo with enough chars",
        source_id="manual:test",
    )
    assert rid is not None
    assert isinstance(rid, str)


def test_insert_record_dedup_by_hash(conn):
    """Same content + same source returns None on second insert."""
    rid1 = insert_record(
        conn, source="manual", timestamp=1717800000,
        content="duplicate content for dedup test",
        source_id="x",
    )
    rid2 = insert_record(
        conn, source="manual", timestamp=1717800001,
        content="duplicate content for dedup test",
        source_id="y",
    )
    assert rid1 is not None
    assert rid2 is None  # deduplicated


def test_count_records(populated_conn):
    assert count_records(populated_conn) == 5
    assert count_records(populated_conn, source="claude") == 2
    assert count_records(populated_conn, source="manual") == 1


def test_list_sources_with_counts(populated_conn):
    counts = dict(list_sources_with_counts(populated_conn))
    assert counts["claude"] == 2
    assert counts["gmail"] == 1
    assert counts["file"] == 1
    assert counts["manual"] == 1


def test_get_session_records(populated_conn):
    records = get_session_records(populated_conn, "claude:s1")
    assert len(records) == 1
    assert "Project Phoenix" in records[0]["content"]


def test_short_records_workflow(conn):
    """Short records can be counted and deleted."""
    insert_record(conn, source="manual", timestamp=1, content="ok", source_id="a")
    insert_record(conn, source="manual", timestamp=2, content="this is a long enough memo that passes the threshold", source_id="b")
    assert count_short_records(conn, min_length=10) == 1
    deleted = delete_short_records(conn, min_length=10)
    assert deleted == 1
    assert count_records(conn) == 1
