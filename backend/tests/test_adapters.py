"""Adapter unit tests: validation, suffix mapping, UTF-8 errors, origin. No I/O."""

import json

import pytest

from app.ingest.adapters import (
    UndecodableUploadError,
    UnparseableUploadError,
    UnsupportedSuffixError,
    adapt_text,
    adapt_upload,
)
from tests.upload_fixtures import (
    blank_pdf_bytes,
    docx_bytes,
    encrypted_pdf_bytes,
    minimal_pdf_bytes,
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
    for filename in ("sheet.xls", "slides.pptx", "nosuffix", "", None):
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


def test_pdf_extracts_text_with_page_count_origin() -> None:
    adapted = adapt_upload("report.pdf", "application/pdf", minimal_pdf_bytes(["Hello PDF"]))
    assert adapted.source_type == "file"
    assert adapted.title == "report"
    assert adapted.content == "Hello PDF"
    assert adapted.origin["adapter"] == "pdf"
    assert adapted.origin["filename"] == "report.pdf"
    assert adapted.origin["suffix"] == ".pdf"
    assert adapted.origin["pages"] == "1"


def test_multipage_pdf_joins_with_blank_line() -> None:
    adapted = adapt_upload(
        "two.pdf", "application/pdf", minimal_pdf_bytes(["page one", "page two"])
    )
    assert adapted.content == "page one\n\npage two"
    assert adapted.origin["pages"] == "2"


def test_uppercase_pdf_and_docx_suffixes_adapt() -> None:
    pdf = adapt_upload("UPPER.PDF", "application/pdf", minimal_pdf_bytes(["x"]))
    assert pdf.origin["adapter"] == "pdf"
    assert pdf.origin["suffix"] == ".pdf"
    assert pdf.title == "UPPER"
    doc = adapt_upload(
        "WORD.DOCX",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        docx_bytes(["y"], []),
    )
    assert doc.origin["adapter"] == "docx"
    assert doc.origin["suffix"] == ".docx"
    assert doc.title == "WORD"


def test_docx_extracts_paragraphs_then_tables() -> None:
    adapted = adapt_upload(
        "notes.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        docx_bytes(["first", "second"], [[["a", "b"], ["c", "d"]]]),
    )
    assert adapted.source_type == "file"
    assert adapted.title == "notes"
    assert adapted.content == "first\nsecond\na | b\nc | d"
    assert adapted.origin["adapter"] == "docx"
    assert "pages" not in adapted.origin


def test_corrupt_pdf_raises_unparseable() -> None:
    with pytest.raises(UnparseableUploadError, match="not a readable PDF"):
        adapt_upload("evil.pdf", "application/pdf", b"%PDF-1.4 garbage, not a pdf")


def test_corrupt_docx_raises_unparseable() -> None:
    with pytest.raises(UnparseableUploadError, match="not a valid .docx"):
        adapt_upload("evil.docx", "application/octet-stream", b"not a zip")


def test_ole_doc_bytes_named_docx_raise_unparseable() -> None:
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
    with pytest.raises(UnparseableUploadError, match="legacy .doc"):
        adapt_upload("legacy.docx", "application/msword", ole)


def test_encrypted_pdf_raises_unparseable() -> None:
    with pytest.raises(UnparseableUploadError, match="encrypted PDFs are not supported"):
        adapt_upload("locked.pdf", "application/pdf", encrypted_pdf_bytes())


def test_blank_page_pdf_adapts_with_empty_content() -> None:
    adapted = adapt_upload("blank.pdf", "application/pdf", blank_pdf_bytes())
    assert adapted.content == ""
    assert adapted.origin["pages"] == "1"
