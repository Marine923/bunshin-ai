"""Tests for the iMessage ingester (pure-Python helpers)."""
from __future__ import annotations

from bunshin.ingestion.imessage import (
    APPLE_EPOCH_OFFSET,
    _apple_date_to_unix,
    _recover_text_from_attributedbody,
)


def test_apple_date_nanoseconds():
    # 2026-06-15 00:00:00 UTC → ns since Apple epoch (2001-01-01)
    nanos = (1781481600 - APPLE_EPOCH_OFFSET) * 1_000_000_000
    assert _apple_date_to_unix(nanos) == 1781481600


def test_apple_date_seconds():
    # Legacy macOS < 10.13 stored seconds since Apple epoch.
    secs = 1781481600 - APPLE_EPOCH_OFFSET
    assert _apple_date_to_unix(secs) == 1781481600


def test_apple_date_zero():
    assert _apple_date_to_unix(0) is None


def test_recover_text_returns_none_on_empty():
    assert _recover_text_from_attributedbody(b"") is None
    assert _recover_text_from_attributedbody(None) is None


def test_recover_text_extracts_visible_string():
    # Simulated typedstream: noise + NSString marker + body + noise.
    body = "こんにちは、明日10時に集合です".encode("utf-8")
    blob = (
        b"\x04\x0bstreamtyped\x81\xe8\x03"
        b"\x84\x01@\x84\x84\x84"
        b"NSAttributedString\x00\x84"
        b"NSString\x01\x01\x95\x84\x01+"
        + body
        + b"\x86\x84\x02NSDictionary"
    )
    out = _recover_text_from_attributedbody(blob)
    assert out is not None
    assert "こんにちは" in out


def test_recover_text_skips_format_classes():
    # Only class names, no real content
    blob = (
        b"\x04\x0bstreamtyped\x84"
        b"NSAttributedString\x00NSString\x00NSDictionary"
    )
    out = _recover_text_from_attributedbody(blob)
    # Should not return a class-name string as "text".
    if out is not None:
        assert "NSAttributed" not in out
        assert "NSDictionary" not in out
