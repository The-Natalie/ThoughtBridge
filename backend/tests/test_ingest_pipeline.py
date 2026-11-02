"""Pipeline + repository tests: persist shape, rollback, caps, dim guard.

Real SQLite (tmp DBs), stubbed embeddings — except the gated real-model
smoke, the suite never touches fastembed.
"""

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

import pytest

import app.db.artifacts as artifacts_mod
from app.db.artifacts import get_artifact_detail, list_artifacts
from app.db.connection import (
    EmbeddingDimMismatchError,
    init_db,
)
from app.db.connection import (
    connect as real_connect,
)
from app.ingest.chunker import chunk_text
from app.ingest.pipeline import ArtifactTooLargeError, ingest_source
from app.retrieval.embedder import embed_passages

MAXC = 500_000
MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384


def stub_embed(texts: list[str]) -> list[list[float]]:
    return [[(i + 1) * 0.01] * DIM for i in range(len(texts))]


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "ingest.db")
    init_db(path)
    return path


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _counts(db_path: str) -> tuple[int, int, int]:
    conn = real_connect(db_path)
    try:
        a = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        c = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        v = conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0]
    finally:
        conn.close()
    return (a, c, v)


def _failing_connect(path: str) -> Any:
    conn = real_connect(path)

    class _FailOnVec:
        def execute(self, sql: Any, *args: Any, **kwargs: Any) -> Any:
            if "chunks_vec" in str(sql):
                raise RuntimeError("forced vec failure")
            return conn.execute(sql, *args, **kwargs)

        def __enter__(self) -> Any:
            conn.__enter__()
            return self

        def __exit__(self, *exc: object) -> Any:
            return conn.__exit__(*exc)

        def __getattr__(self, name: str) -> Any:
            return getattr(conn, name)

    return _FailOnVec()


def test_round_trip_persists_artifact_chunks_and_both_indexes(db_path: str) -> None:
    content = "Fixed the lazy loading problem with selectinload on the query."
    result = ingest_source(
        db_path=db_path,
        source_type="note",
        title="t",
        content=content,
        origin={"adapter": "text"},
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=stub_embed,
    )
    assert len(result.artifact_id) == 32
    assert result.chunk_count >= 1
    assert _counts(db_path) == (1, result.chunk_count, result.chunk_count)
    conn = real_connect(db_path)
    try:
        fts = conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'selectinload'"
        ).fetchone()[0]
        first_id = conn.execute("SELECT id FROM chunks ORDER BY chunk_idx LIMIT 1").fetchone()[0]
        nearest = conn.execute(
            "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
            (_pack([0.01] * DIM),),
        ).fetchone()[0]
    finally:
        conn.close()
    assert fts == 1
    assert nearest == first_id


def test_embed_failure_persists_nothing(db_path: str) -> None:
    def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model exploded")

    with pytest.raises(RuntimeError):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content="selectinload content here",
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=boom,
        )
    assert _counts(db_path) == (0, 0, 0)
    conn = real_connect(db_path)
    try:
        fts = conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'selectinload'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert fts == 0


def test_in_transaction_rollback_leaves_zero_rows(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts_mod, "connect", _failing_connect)
    with pytest.raises(RuntimeError, match="forced vec failure"):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content="selectinload content here",
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=stub_embed,
        )
    assert _counts(db_path) == (0, 0, 0)
    conn = real_connect(db_path)
    try:
        fts = conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'selectinload'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert fts == 0


def test_char_cap_rejects_without_persisting(db_path: str) -> None:
    with pytest.raises(ArtifactTooLargeError):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content="x" * (MAXC + 1),
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=stub_embed,
        )
    assert _counts(db_path) == (0, 0, 0)


def test_dim_guard_fails_before_embedding(db_path: str) -> None:
    conn = real_connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE meta SET value = 'other' WHERE key = 'embedding_model'")
    finally:
        conn.close()
    called: list[list[str]] = []

    def spy(texts: list[str]) -> list[list[float]]:
        called.append(texts)
        return stub_embed(texts)

    with pytest.raises(EmbeddingDimMismatchError):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content="hello",
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=spy,
        )
    assert called == []
    assert _counts(db_path) == (0, 0, 0)


def test_wrong_dim_and_wrong_count_vectors_rejected(db_path: str) -> None:
    content = "first para here.\n\nsecond para here for two chunks maybe not"
    with pytest.raises(ValueError, match="dim"):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content=content,
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=lambda texts: [[0.0] * 128 for _ in texts],
        )
    assert _counts(db_path) == (0, 0, 0)
    with pytest.raises(ValueError, match="chunks but"):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title="t",
            content=content,
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=lambda texts: [],
        )
    assert _counts(db_path) == (0, 0, 0)


def test_embed_passages_empty_never_touches_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_load(name: str = "") -> Any:
        raise AssertionError("model must not load for empty input")

    monkeypatch.setattr("app.retrieval.embedder.get_model", must_not_load)
    assert embed_passages([]) == []


def test_list_artifacts_counts(db_path: str) -> None:
    for title in ("one", "two"):
        ingest_source(
            db_path=db_path,
            source_type="note",
            title=title,
            content=f"content for {title} with selectinload",
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=stub_embed,
        )
    items = list_artifacts(db_path)
    assert len(items) == 2
    for item in items:
        assert item.chunk_count >= 1
        assert item.fact_count == 0


def test_get_artifact_detail_round_trip(db_path: str) -> None:
    content = "detail round trip with selectinload inside the body."
    origin = {"adapter": "text"}
    result = ingest_source(
        db_path=db_path,
        source_type="paste",
        title="detail title",
        content=content,
        origin=origin,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=stub_embed,
    )
    detail = get_artifact_detail(db_path, result.artifact_id)
    assert detail is not None
    assert detail.content == content
    assert detail.content_hash == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert json.loads(detail.origin) == origin
    assert detail.title == "detail title"
    assert detail.source_type == "paste"
    expected = chunk_text(content)
    assert len(detail.chunks) == len(expected)
    for got, want in zip(detail.chunks, expected):
        assert (got.chunk_idx, got.span_start, got.span_end, got.text) == (
            want.chunk_idx,
            want.span_start,
            want.span_end,
            want.text,
        )
    assert detail.fact_ids == []
    assert detail.interpretation_ids == []


def test_get_artifact_detail_missing_returns_none(db_path: str) -> None:
    assert get_artifact_detail(db_path, "no-such-id") is None


@pytest.mark.skipif(
    os.environ.get("TB_REAL_EMBEDDINGS") != "1", reason="needs network + ~90MB model"
)
def test_real_embedding_smoke(db_path: str) -> None:
    result = ingest_source(
        db_path=db_path,
        source_type="note",
        title="smoke",
        content="selectinload smoke content",
        origin={"adapter": "text"},
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=None,
    )
    assert result.chunk_count >= 1
    conn = real_connect(db_path)
    try:
        blobs = conn.execute("SELECT embedding FROM chunks_vec").fetchall()
    finally:
        conn.close()
    assert len(blobs) == result.chunk_count
    assert len(struct.unpack(f"{DIM}f", blobs[0][0])) == DIM
