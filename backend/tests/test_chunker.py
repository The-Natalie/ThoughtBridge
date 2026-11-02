"""Chunker unit tests: spans, overlap, boundaries, empty/long inputs. Pure — no DB."""

import itertools

from app.ingest.chunker import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS, chunk_text


def test_short_text_single_chunk_exact_span() -> None:
    content = "Fixed the lazy loading problem by adding selectinload to the query."
    chunks = chunk_text(content)
    assert len(chunks) == 1
    assert (chunks[0].span_start, chunks[0].span_end) == (0, len(content))
    assert content[chunks[0].span_start : chunks[0].span_end] == chunks[0].text
    assert chunks[0].chunk_idx == 0


def test_multi_paragraph_spans_round_trip_and_idx_sequential() -> None:
    content = "\n\n".join(f"Paragraph {i} with enough words to matter. " * 12 for i in range(8))
    assert len(content) > CHUNK_TARGET_CHARS
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_idx == i
        assert content[chunk.span_start : chunk.span_end] == chunk.text


def test_overlap_shared_substring_between_consecutive_chunks() -> None:
    content = "a" * 600 + "\n\n" + "b" * 600 + "\n\n" + "c" * 600
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    for prev, nxt in itertools.pairwise(chunks):
        assert nxt.text[:CHUNK_OVERLAP_CHARS] == prev.text[-CHUNK_OVERLAP_CHARS:]


def test_deterministic_repeat_calls_identical() -> None:
    content = "\n\n".join(f"Determinism paragraph {i}. " * 20 for i in range(6))
    first = chunk_text(content)
    second = chunk_text(content)
    assert [(c.text, c.span_start, c.span_end, c.chunk_idx) for c in first] == [
        (c.text, c.span_start, c.span_end, c.chunk_idx) for c in second
    ]


def test_empty_and_whitespace_yield_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\t  \n  ") == []


def test_single_long_paragraph_splits_with_bounded_chunks() -> None:
    sentences = [f"Sentence number {i} carries filler words to add length. " for i in range(110)]
    content = "".join(sentences)
    assert len(content) > 5000
    assert "\n" not in content
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    longest_sentence = max(len(s) for s in content.split(". "))
    for chunk in chunks:
        assert content[chunk.span_start : chunk.span_end] == chunk.text
        assert len(chunk.text) <= CHUNK_TARGET_CHARS + CHUNK_OVERLAP_CHARS + longest_sentence


def test_spans_within_bounds_and_non_decreasing() -> None:
    content = "a" * 600 + "\n\n" + "b" * 600 + "\n\n" + "c" * 600
    chunks = chunk_text(content)
    starts = [c.span_start for c in chunks]
    assert starts == sorted(starts)
    for chunk in chunks:
        assert 0 <= chunk.span_start <= chunk.span_end <= len(content)


def test_exact_target_length_stays_single_chunk() -> None:
    content = "x" * CHUNK_TARGET_CHARS
    chunks = chunk_text(content)
    assert len(chunks) == 1
    assert (chunks[0].span_start, chunks[0].span_end) == (0, CHUNK_TARGET_CHARS)


def test_crlf_paragraphs_split_with_exact_spans() -> None:
    content = "a" * 600 + "\r\n\r\n" + "b" * 600
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    assert chunks[0].text == "a" * 600
    for chunk in chunks:
        assert content[chunk.span_start : chunk.span_end] == chunk.text


def test_multibyte_spans_are_char_offsets() -> None:
    content = "héllo wörld 🎉 " * 100 + "\n\n" + "日本語テスト " * 120
    assert len(content.encode("utf-8")) > len(content)  # multibyte present
    chunks = chunk_text(content)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert content[chunk.span_start : chunk.span_end] == chunk.text
