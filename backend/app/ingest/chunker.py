"""Deterministic paragraph-aware text chunker with exact source spans.

Pure stdlib: no app imports, no I/O, no randomness. Every chunk satisfies
``content[span_start:span_end] == text`` against the ORIGINAL input string.
"""

from __future__ import annotations

from dataclasses import dataclass

CHUNK_TARGET_CHARS = 1000
CHUNK_OVERLAP_CHARS = 150

_PARAGRAPH_SEPS = ("\r\n\r\n", "\n\n")
_SENTENCE_ENDS = (". ", "! ", "? ", ".\n", "!\n", "?\n", ".\r", "!\r", "?\r")
_WORD_BREAKS = (" ", "\t", "\n", "\r")


@dataclass
class Chunk:
    """One searchable passage with its exact span in the source content."""

    text: str
    span_start: int
    span_end: int
    chunk_idx: int


def _find_cut(content: str, pos: int, limit: int) -> int:
    """Return a cut offset in ``(pos, limit]``.

    Prefers a paragraph boundary, then a sentence boundary, then a word
    break, falling back to a hard cut at ``limit``. Always returns an
    offset strictly greater than ``pos`` so callers always make progress.
    """
    seg = content[pos:limit]
    para = max(seg.rfind(sep) for sep in _PARAGRAPH_SEPS)
    if para > 0:
        return pos + para
    sent = max(seg.rfind(end) for end in _SENTENCE_ENDS)
    if sent >= 0:
        return pos + sent + 1
    word = max(seg.rfind(brk) for brk in _WORD_BREAKS)
    if word > 0:
        return pos + word
    return limit


def chunk_text(content: str) -> list[Chunk]:
    """Split ``content`` into overlapping chunks with exact spans.

    Greedy paragraph packing: accumulate paragraphs until the next would
    exceed ``CHUNK_TARGET_CHARS``, then cut at the last paragraph/sentence/
    word boundary (hard cut as final fallback). The next window starts
    ``CHUNK_OVERLAP_CHARS`` before the previous chunk's stripped end so
    consecutive chunks share context. Each chunk's text is stripped for
    embedding quality while its span covers the stripped slice exactly.

    Empty or whitespace-only input yields ``[]``; callers decide whether
    that is a 400/422. Deterministic: same input, same chunks.
    """
    if not content.strip():
        return []
    chunks: list[Chunk] = []
    total = len(content)
    pos = 0
    while pos < total:
        if total - pos <= CHUNK_TARGET_CHARS:
            raw_end = total
        else:
            raw_end = _find_cut(content, pos, pos + CHUNK_TARGET_CHARS)
        raw = content[pos:raw_end]
        stripped = raw.strip()
        if not stripped:
            pos = raw_end
            continue
        start = pos + (len(raw) - len(raw.lstrip()))
        end = start + len(stripped)
        chunks.append(Chunk(text=stripped, span_start=start, span_end=end, chunk_idx=len(chunks)))
        if raw_end >= total:
            break
        nxt = end - CHUNK_OVERLAP_CHARS
        pos = nxt if nxt > pos else raw_end
    return chunks
