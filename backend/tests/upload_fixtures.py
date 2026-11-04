"""Shared PDF/DOCX fixture builders for upload-adapter tests.

All fixtures are generated in code — no binary blobs committed. The minimal
PDF is assembled programmatically with computed xref offsets so it stays
valid without magic numbers.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document
from pypdf import PdfWriter


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def minimal_pdf_bytes(pages: list[str]) -> bytes:
    """Build a valid PDF with one text line per page (1–2 pages typical)."""
    assert pages, "fixture needs at least one page"
    # Object layout: 1=catalog, 2=pages, then per page (page, content), then font.
    font_num = 3 + 2 * len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
    ]
    for i, text in enumerate(pages):
        page_num = 3 + 2 * i
        stream = f"BT /F1 12 Tf 10 10 Td ({_escape_pdf_text(text)}) Tj ET".encode("ascii")
        bodies.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {page_num + 1} 0 R >>".encode("ascii")
        )
        bodies.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    bodies.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for num, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def docx_bytes(paragraphs: list[str], tables: list[list[list[str]]]) -> bytes:
    """Build a .docx with the given paragraphs, then tables (rows of cells)."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    for rows in tables:
        table = doc.add_table(rows=len(rows), cols=len(rows[0]))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def encrypted_pdf_bytes() -> bytes:
    """Build a password-encrypted PDF (unreadable without the password)."""
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.encrypt("pw")
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def blank_pdf_bytes() -> bytes:
    """Build a valid PDF whose pages extract to no text (blank page)."""
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()
