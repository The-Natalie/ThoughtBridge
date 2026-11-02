"""Local embedding wrapper: fastembed ``TextEmbedding`` behind a lazy singleton.

Only this module touches fastembed. Documents use ``passage_embed`` and
queries use ``query_embed`` (BGE asymmetric retrieval). The model is never
instantiated at import time, so importing this module is fast and
offline-safe. Tests inject stubs through the pipeline's ``embed_fn`` param
or the search's ``embed_fn`` param and never reach the real model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
EMBEDDING_MODEL_DEFAULT = "BAAI/bge-small-en-v1.5"

EmbedFn = Callable[[list[str]], list[list[float]]]
QueryEmbedFn = Callable[[str], list[float]]

_cached: tuple[str, TextEmbedding] | None = None


def get_model(model_name: str = EMBEDDING_MODEL_DEFAULT) -> TextEmbedding:
    """Return the cached model, loading (downloading on first use) as needed."""
    global _cached
    if _cached is not None and _cached[0] == model_name:
        return _cached[1]
    logger.info("loading embedding model: %s", model_name)
    model = TextEmbedding(model_name=model_name)
    _cached = (model_name, model)
    return model


def embed_passages(
    texts: list[str], model_name: str = EMBEDDING_MODEL_DEFAULT
) -> list[list[float]]:
    """Embed document passages to ``list[list[float]]`` (one vector per text)."""
    if not texts:
        return []
    model = get_model(model_name)
    return [list(map(float, vec)) for vec in model.passage_embed(texts)]


def embed_query(text: str, model_name: str = EMBEDDING_MODEL_DEFAULT) -> list[float]:
    """Embed one search query to ``list[float]`` via ``query_embed``.

    Assumes non-blank input (the router rejects blank queries with 422
    before calling); a blank string here raises ``ValueError`` as
    defense-in-depth.
    """
    if not text.strip():
        raise ValueError("query must not be blank")
    model = get_model(model_name)
    return list(map(float, next(iter(model.query_embed(text)))))
