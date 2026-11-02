"""Adapter unit tests: validation, suffix mapping, UTF-8 errors, origin. No I/O."""

import json

import pytest

from app.ingest.adapters import (
    UndecodableUploadError,
    UnsupportedSuffixError,
    adapt_text,
    adapt_upload,
)


def test_text_types_adapt_with_title_and_origin() -> None:
    for source_type in ("note", "paste", "summary"):
        adapted = adapt_text(source_type, "  My title  ", "body text")
        assert adapted.source_type == source_type
        assert adapted.title == "My title"
        assert adapted.content == "body text"
        assert adapted.origin["adapter"] == "text"


def test_unknown_source_type_raises() -> None:
    with pytest.raises(ValueError):
        adapt_text("email", "t", "body")


def test_txt_md_and_uppercase_suffixes_adapt() -> None:
    for filename, stem in (("note.txt", "note"), ("log.md", "log"), ("UPPER.MD", "UPPER")):
        adapted = adapt_upload(filename, "text/plain", b"# hello")
        assert adapted.source_type == "file"
        assert adapted.title == stem
        assert adapted.content == "# hello"
        assert adapted.origin["adapter"] == "txt_md"
        assert adapted.origin["filename"] == filename
        assert adapted.origin["suffix"] in (".txt", ".md")


def test_bad_suffixes_and_missing_filenames_raise() -> None:
    for filename in ("doc.pdf", "doc.docx", "nosuffix", "", None):
        with pytest.raises(UnsupportedSuffixError):
            adapt_upload(filename, "text/plain", b"body")


def test_invalid_utf8_raises() -> None:
    with pytest.raises(UndecodableUploadError):
        adapt_upload("bad.txt", "text/plain", b"\xff\xfe bad")


def test_origin_json_round_trips() -> None:
    adapted = adapt_upload("note.md", "text/markdown", b"body")
    assert json.loads(json.dumps(adapted.origin)) == adapted.origin


def test_mislabeled_content_type_still_adapts() -> None:
    adapted = adapt_upload("note.md", "application/octet-stream", b"body")
    assert adapted.source_type == "file"
    assert adapted.origin["suffix"] == ".md"
