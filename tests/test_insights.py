"""Tests for bunshin.insights."""
from bunshin.insights import generate_insights, parse_projects_from_memory


def test_generate_insights_shape(conn):
    """Even on an empty DB, generate_insights returns the expected structure."""
    out = generate_insights(conn)
    for key in ("generated_at", "inactive_projects", "upcoming_events", "recent_notes", "pending_questions", "setup_hints"):
        assert key in out
    assert isinstance(out["inactive_projects"], list)
    assert isinstance(out["upcoming_events"], list)
    assert isinstance(out["recent_notes"], list)
    assert isinstance(out["pending_questions"], list)
    assert isinstance(out["setup_hints"], list)


def test_parse_projects_from_memory_returns_list():
    """Always returns a list (even when MEMORY.md is missing)."""
    projects = parse_projects_from_memory()
    assert isinstance(projects, list)
