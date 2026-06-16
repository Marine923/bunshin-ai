"""Shared pytest fixtures."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from bunshin.storage import init_db


@pytest.fixture
def tmp_db_path(tmp_path):
    """Path to an isolated test DB file."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(tmp_db_path):
    """Initialized SQLite connection on a temp DB. Auto-closed."""
    c = init_db(tmp_db_path)
    yield c
    c.close()


@pytest.fixture
def populated_conn(conn):
    """A conn with a small set of pre-inserted records for search/KG tests."""
    from bunshin.storage import insert_record

    fixtures = [
        ("claude", "Project PhoenixのMVP launchについて話した", "claude:s1", 1717800000, {"role": "assistant"}),
        ("claude", "Acme Foundationのregional sponsorship、年300万円の提案", "claude:s2", 1717810000, {"role": "assistant"}),
        ("gmail", "Subject: Globex Corp ミーティング\n来週火曜10時に確認をお願いします", "msg-1", 1717820000, {"subject": "Globex Corp", "from": "client@example.com"}),
        ("file", "# 設計書 v0\n\n4条件: ローカル, AI-Agnostic, オフライン, オムニソース", "/tmp/design.md", 1717830000, {"path": "/tmp/design.md"}),
        ("manual", "覚えといて: 来週月曜にドローン点検", "manual:1", 1717840000, {"kind": "memo"}),
    ]
    for source, content, source_id, ts, meta in fixtures:
        insert_record(conn, source=source, timestamp=ts, content=content, source_id=source_id, metadata=meta)
    return conn
