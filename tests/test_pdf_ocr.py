"""Tests for the scanned-PDF OCR fallback logic in files.py.

The Vision OCR pipeline itself is macOS-only, so here we just exercise
the threshold (when to call the fallback) and verify that _read_pdf
returns the OCR result when it's substantially longer than the
embedded text.
"""
from __future__ import annotations

from unittest.mock import patch

from bunshin.ingestion import files


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, page_texts):
        self.pages = [_FakePage(t) for t in page_texts]
        self.is_encrypted = False


def test_scanned_pdf_triggers_ocr_fallback(tmp_path, monkeypatch):
    fake_pdf = tmp_path / "scanned.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        "pypdf.PdfReader",
        lambda _: _FakeReader(["", "", ""]),  # 3 pages, zero text
    )
    monkeypatch.setattr(
        files,
        "_ocr_pdf_fallback",
        lambda _: "OCRで復元したテキスト",
    )

    result = files._read_pdf(fake_pdf)
    assert result == "OCRで復元したテキスト"


def test_text_pdf_skips_ocr_fallback(tmp_path, monkeypatch):
    fake_pdf = tmp_path / "digital.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    text = "ABC " * 100  # 400 chars on a single page → far above 20
    monkeypatch.setattr(
        "pypdf.PdfReader",
        lambda _: _FakeReader([text]),
    )
    called = {"ocr": False}

    def _spy_ocr(_):
        called["ocr"] = True
        return "should not be used"

    monkeypatch.setattr(files, "_ocr_pdf_fallback", _spy_ocr)

    result = files._read_pdf(fake_pdf)
    assert result is not None
    assert "ABC" in result
    assert called["ocr"] is False


def test_ocr_fallback_only_used_when_longer(tmp_path, monkeypatch):
    """If OCR returns less text than pypdf, prefer pypdf's text."""
    fake_pdf = tmp_path / "low.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    # 10 chars on each of 2 pages → avg 10 → fallback triggered
    monkeypatch.setattr(
        "pypdf.PdfReader",
        lambda _: _FakeReader(["1234567890", "abcdefghij"]),
    )
    monkeypatch.setattr(
        files,
        "_ocr_pdf_fallback",
        lambda _: "X",  # shorter than the direct text
    )

    result = files._read_pdf(fake_pdf)
    assert result is not None
    assert "1234567890" in result
    assert "X" != result
