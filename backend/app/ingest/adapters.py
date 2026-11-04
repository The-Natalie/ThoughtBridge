"""Source adapters: every input becomes a normalized ``AdaptedSource`` (PRD TS-2).

Content is untrusted data, never instructions — this module performs no
prompt construction and never interprets content beyond validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from docx import Document
from pypdf import PdfReader

TEXT_SOURCE_TYPES = frozenset({"note", "paste", "summary"})
ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}
UPLOAD_SOURCE_TYPE = "file"
TB_CONVERSATION_SOURCE_TYPE = "tb_conversation"
ROLE_TAGS = {"user": "User:", "assistant": "Assistant:"}
CONVERSATION_TITLE_CHARS = 60


class UnsupportedSuffixError(ValueError):
    """Upload filename has no usable text suffix."""


class UndecodableUploadError(ValueError):
    """Upload bytes are not valid UTF-8 text."""


class UnparseableUploadError(ValueError):
    """Upload bytes fail format parsing (corrupt/encrypted/unsupported)."""


@dataclass
class AdaptedSource:
    """Normalized ingestion input: every adapter produces this shape."""

    source_type: str
    title: str
    content: str
    origin: dict[str, str] = field(default_factory=dict)


class SourceAdapter(Protocol):
    """Seam future capture methods plug into (PDF/Word, tb_conversation)."""

    source_types: frozenset[str]

    def adapt(self, payload: Any) -> AdaptedSource: ...


def adapt_text(source_type: str, title: str, content: str) -> AdaptedSource:
    """Normalize typed/pasted text. Unknown ``source_type`` raises ValueError."""
    if source_type not in TEXT_SOURCE_TYPES:
        raise ValueError(f"unknown source_type: {source_type!r}")
    return AdaptedSource(
        source_type=source_type,
        title=title.strip(),
        content=content,
        origin={"adapter": "text"},
    )


def adapt_conversation(
    conversation_id: str,
    kind: str,
    turns: list[tuple[str, str]],
    turn_start: int,
) -> AdaptedSource:
    """Normalize one turn-append as a role-tagged ``tb_conversation`` source.

    Each turn is ``(role, content)`` with role in ``{"user", "assistant"}``.
    Contents are used verbatim (no strip — spans must match the stored
    artifact exactly; the chunker strips per-chunk). Empty ``turns`` or an
    unknown role raises ValueError.
    """
    if not turns:
        raise ValueError("conversation append holds no turns")
    for role, _ in turns:
        if role not in ROLE_TAGS:
            raise ValueError(f"unknown turn role: {role!r}")
    content = "\n\n".join(f"{ROLE_TAGS[role]} {text}" for role, text in turns)
    first_user = next((text for role, text in turns if role == "user"), None)
    title = first_user[:CONVERSATION_TITLE_CHARS] if first_user else f"{kind} conversation"
    return AdaptedSource(
        source_type=TB_CONVERSATION_SOURCE_TYPE,
        title=title,
        content=content,
        origin={
            "adapter": "tb_conversation",
            "conversation_id": conversation_id,
            "kind": kind,
            "turn_start": str(turn_start),
            "turn_end": str(turn_start + len(turns) - 1),
        },
    )


def _adapt_pdf(filename: str, content_type: str | None, raw: bytes) -> AdaptedSource:
    """Normalize a text-based `.pdf` upload. Suffix rules; MIME is recorded, not trusted."""
    try:
        reader = PdfReader(BytesIO(raw))
        # decrypt("") returns 0/falsy when the empty password fails.
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnparseableUploadError("encrypted PDFs are not supported")
        texts = [(page.extract_text() or "") for page in reader.pages]
        page_count = len(reader.pages)
    except UnparseableUploadError:
        raise
    # Broad catch by design: parsers raise KeyError/TypeError/AttributeError/etc.
    # on malformed input; everything maps to 400. (No noqa: BLE001 exempts
    # handlers that re-raise, so none is needed here.)
    except Exception as exc:
        raise UnparseableUploadError("upload is not a readable PDF") from exc
    content = "\n\n".join(t for t in (text.strip() for text in texts) if t)
    return AdaptedSource(
        source_type=UPLOAD_SOURCE_TYPE,
        title=Path(filename).stem.strip(),
        content=content,
        origin={
            "adapter": "pdf",
            "filename": filename,
            "suffix": ".pdf",
            "content_type": content_type or "",
            "pages": str(page_count),
        },
    )


def _adapt_docx(filename: str, content_type: str | None, raw: bytes) -> AdaptedSource:
    """Normalize a `.docx` upload: paragraphs, then tables. MIME is recorded, not trusted."""
    # Headers/footers/footnotes deliberately not extracted (MVP scope).
    # Tables are appended after paragraphs rather than interleaved in
    # document order (that would require walking the OOXML body).
    try:
        doc = Document(BytesIO(raw))
        blocks = [p.text.strip() for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
    except UnparseableUploadError:
        raise
    # Broad catch by design, same rationale as _adapt_pdf (no noqa needed: re-raise).
    except Exception as exc:
        raise UnparseableUploadError(
            "upload is not a valid .docx file (legacy .doc is not supported)"
        ) from exc
    content = "\n".join(block for block in blocks if block)
    return AdaptedSource(
        source_type=UPLOAD_SOURCE_TYPE,
        title=Path(filename).stem.strip(),
        content=content,
        origin={
            "adapter": "docx",
            "filename": filename,
            "suffix": ".docx",
            "content_type": content_type or "",
        },
    )


def adapt_upload(filename: str | None, content_type: str | None, raw: bytes) -> AdaptedSource:
    """Normalize a file upload. Suffix rules; MIME is recorded, not trusted."""
    if not filename:
        raise UnsupportedSuffixError("upload is missing a filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise UnsupportedSuffixError(f"unsupported upload suffix for {filename!r}")
    if suffix == ".pdf":
        return _adapt_pdf(filename, content_type, raw)
    if suffix == ".docx":
        return _adapt_docx(filename, content_type, raw)
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UndecodableUploadError("upload is not valid UTF-8 text") from exc
    return AdaptedSource(
        source_type=UPLOAD_SOURCE_TYPE,
        title=Path(filename).stem.strip(),
        content=content,
        origin={
            "adapter": "txt_md",
            "filename": filename,
            "suffix": suffix,
            "content_type": content_type or "",
        },
    )
