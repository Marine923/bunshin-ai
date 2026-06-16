"""Tests for the Apple Notes ingester (parser + HTML conversion).

The AppleScript itself can only run on macOS with Notes.app installed, so
these tests focus on the pure-Python pieces: HTML→text conversion, date
parsing, and parsing the AppleScript output stream.
"""
from __future__ import annotations

from bunshin.ingestion.notes import (
    _parse_applescript_date,
    html_to_text,
    parse_notes_output,
)


def test_html_to_text_strips_tags():
    html = "<div><p>こんにちは</p><p>Hello <b>world</b></p></div>"
    assert "こんにちは" in html_to_text(html)
    assert "Hello world" in html_to_text(html)
    assert "<" not in html_to_text(html)


def test_html_to_text_preserves_line_breaks():
    html = "<p>line1</p><p>line2</p>"
    text = html_to_text(html)
    assert "line1" in text
    assert "line2" in text
    assert text.index("line1") < text.index("line2")
    # paragraphs should be separated by at least one newline
    assert "\n" in text


def test_html_to_text_drops_script_and_style():
    html = "<style>p{color:red}</style><p>visible</p><script>alert(1)</script>"
    text = html_to_text(html)
    assert "visible" in text
    assert "color" not in text
    assert "alert" not in text


def test_html_to_text_handles_lists_and_tables():
    html = "<ul><li>one</li><li>two</li></ul><table><tr><td>a</td><td>b</td></tr></table>"
    text = html_to_text(html)
    assert "one" in text and "two" in text
    assert "a" in text and "b" in text


def test_parse_applescript_date_english():
    # "Monday, June 16, 2026 at 10:30:00 AM"
    ts = _parse_applescript_date("Monday, June 16, 2026 at 10:30:00 AM")
    assert ts is not None
    assert ts > 0


def test_parse_applescript_date_japanese():
    # Pre-Monterey style (no space after 日)
    ts = _parse_applescript_date("2026年6月16日月曜日 10:30:00")
    assert ts is not None
    assert ts > 0
    # Monterey+ style (space between 日 and weekday)
    ts2 = _parse_applescript_date("2026年6月15日 月曜日 15:47:28")
    assert ts2 is not None
    assert ts2 > 0


def test_parse_applescript_date_empty_returns_none():
    assert _parse_applescript_date("") is None
    assert _parse_applescript_date("   ") is None
    assert _parse_applescript_date("not a date") is None


def test_parse_notes_output_basic():
    raw = (
        "x-coredata://abc/1"
        "<<<BUNSHIN_FIELD>>>テストノート"
        "<<<BUNSHIN_FIELD>>>Monday, June 16, 2026 at 10:30:00 AM"
        "<<<BUNSHIN_FIELD>>>Sunday, June 15, 2026 at 09:00:00 AM"
        "<<<BUNSHIN_FIELD>>>仕事"
        "<<<BUNSHIN_FIELD>>><p>本文です</p>"
        "<<<BUNSHIN_NOTE_END>>>"
    )
    notes = parse_notes_output(raw)
    assert len(notes) == 1
    n = notes[0]
    assert n["id"] == "x-coredata://abc/1"
    assert n["name"] == "テストノート"
    assert n["folder"] == "仕事"
    assert n["modified"] is not None
    assert n["created"] is not None
    assert "本文です" in n["body_html"]


def test_parse_notes_output_multiple_notes():
    raw = (
        "id1<<<BUNSHIN_FIELD>>>title1<<<BUNSHIN_FIELD>>>"
        "Monday, June 16, 2026 at 10:30:00 AM<<<BUNSHIN_FIELD>>>"
        "Sunday, June 15, 2026 at 09:00:00 AM<<<BUNSHIN_FIELD>>>"
        "folder1<<<BUNSHIN_FIELD>>>body1"
        "<<<BUNSHIN_NOTE_END>>>"
        "id2<<<BUNSHIN_FIELD>>>title2<<<BUNSHIN_FIELD>>>"
        "Tuesday, June 17, 2026 at 11:00:00 AM<<<BUNSHIN_FIELD>>>"
        "Monday, June 16, 2026 at 09:00:00 AM<<<BUNSHIN_FIELD>>>"
        "folder2<<<BUNSHIN_FIELD>>>body2"
        "<<<BUNSHIN_NOTE_END>>>"
    )
    notes = parse_notes_output(raw)
    assert len(notes) == 2
    assert notes[0]["id"] == "id1"
    assert notes[1]["id"] == "id2"
    assert notes[0]["name"] == "title1"
    assert notes[1]["folder"] == "folder2"


def test_parse_notes_output_ignores_blank_blocks():
    raw = "\n\n<<<BUNSHIN_NOTE_END>>>\n\n"
    assert parse_notes_output(raw) == []


def test_parse_notes_output_skips_malformed():
    raw = (
        "only-one-field<<<BUNSHIN_NOTE_END>>>"
        "id<<<BUNSHIN_FIELD>>>name<<<BUNSHIN_FIELD>>>mod"
        "<<<BUNSHIN_FIELD>>>created<<<BUNSHIN_FIELD>>>folder"
        "<<<BUNSHIN_FIELD>>>body<<<BUNSHIN_NOTE_END>>>"
    )
    notes = parse_notes_output(raw)
    assert len(notes) == 1
    assert notes[0]["id"] == "id"
