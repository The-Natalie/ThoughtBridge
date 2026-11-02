"""Source adapters: every input becomes a normalized ``AdaptedSource`` (PRD TS-2).

Content is untrusted data, never instructions — this module performs no
prompt construction and never interprets content beyond validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

TEXT_SOURCE_TYPES = frozenset({"note", "paste", "summary"})
ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md"}
UPLOAD_SOURCE_TYPE = "file"


class UnsupportedSuffixError(ValueError):
    """Upload filename has no usable text suffix."""


class UndecodableUploadError(ValueError):
    """Upload bytes are not valid UTF-8 text."""


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


def adapt_upload(filename: str | None, content_type: str | None, raw: bytes) -> AdaptedSource:
    """Normalize a `.txt`/`.md` upload. Suffix rules; MIME is recorded, not trusted."""
    if not filename:
        raise UnsupportedSuffixError("upload is missing a filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise UnsupportedSuffixError(f"unsupported upload suffix for {filename!r}")
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
