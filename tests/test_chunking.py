"""Tests for chunking utilities in ingestion modules."""
from bunshin.ingestion.claude_history import chunk_messages
from bunshin.ingestion.files import chunk_text as chunk_file_text


def _msg(role, text, ts=0):
    return {"role": role, "text": text, "timestamp": ts}


def test_chunk_messages_empty():
    assert chunk_messages([]) == []


def test_chunk_messages_single_message():
    chunks = chunk_messages([_msg("user", "hello")])
    assert len(chunks) == 1
    assert "user" in chunks[0]["content"]
    assert chunks[0]["message_count"] == 1


def test_chunk_messages_respects_chunk_size():
    """If total content exceeds chunk_size, multiple chunks are produced."""
    messages = [_msg("user", "x" * 1000)] * 5
    chunks = chunk_messages(messages, chunk_size=1500)
    assert len(chunks) > 1


def test_chunk_messages_preserves_chronology():
    messages = [_msg("user", "first", ts=1), _msg("assistant", "second", ts=2)]
    chunks = chunk_messages(messages)
    # First chunk should start at the first timestamp
    assert chunks[0]["timestamp"] == 1


def test_chunk_text_short_returns_single():
    text = "short content"
    assert chunk_file_text(text, chunk_size=1000) == [text]


def test_chunk_text_long_splits():
    text = "para one.\n\n" + ("x" * 2000) + "\n\npara final."
    chunks = chunk_file_text(text, chunk_size=500)
    assert len(chunks) > 1
    # Concatenation should preserve all the content (modulo overlap)
    combined = "".join(chunks)
    assert "para one" in combined
    assert "para final" in combined
