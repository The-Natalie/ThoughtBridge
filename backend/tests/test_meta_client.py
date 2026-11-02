"""Meta client tests: recorded model ID, probe mapping, truncation, key hygiene.

Every probe test is offline — HTTP is stubbed via httpx.MockTransport, never
a real AsyncClient.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.meta_client import (
    DEFAULT_META_MODEL,
    MAX_ERROR_CHARS,
    ProbeResult,
    check_meta_reachability,
)

CANARY = "canary-key-xyz"
MODEL = "muse-spark-1.3"


@pytest.fixture(autouse=True)
def _clean_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for var in (
        "MODEL_API_KEY",
        "META_MODEL",
        "DATABASE_PATH",
        "EMBEDDING_MODEL",
        "MAX_UPLOAD_MB",
        "MAX_ARTIFACT_CHARS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    get_settings.cache_clear()


def _probe(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> ProbeResult:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return asyncio.run(check_meta_reachability(CANARY, MODEL, client=client, **kwargs))


def test_default_model_id_is_recorded() -> None:
    assert DEFAULT_META_MODEL == "muse-spark-1.3"


def test_settings_default_matches_client_constant() -> None:
    assert Settings(_env_file=None).meta_model == DEFAULT_META_MODEL


def test_probe_200_model_listed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == f"Bearer {CANARY}"
        return httpx.Response(200, json={"data": [{"id": MODEL}, {"id": "other"}]})

    result = _probe(handler)
    assert result.ok is True
    assert result.error is None
    assert result.status_code == 200


def test_probe_200_model_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "other-model"}]})

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert MODEL in result.error
    assert "not listed" in result.error
    assert CANARY not in result.error
    assert result.status_code == 200


@pytest.mark.parametrize("body", ["not-json{{{", '{"unexpected": "shape"}'])
def test_probe_200_bad_body(body: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert "unexpected" in result.error
    assert result.status_code == 200


def test_probe_401_reported_honestly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized nope")

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert "401" in result.error
    assert CANARY not in result.error
    assert result.status_code == 401


def test_probe_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert "timed" in result.error.lower()
    assert result.status_code is None


def test_probe_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert "connection failed" in result.error
    assert CANARY not in result.error
    assert result.status_code is None


def test_probe_long_body_truncated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="x" * 1000)

    result = _probe(handler)
    assert result.ok is False
    assert result.error is not None
    assert CANARY not in result.error
    assert len(result.error) <= len("Meta API models probe: HTTP 500: ") + MAX_ERROR_CHARS


def test_probe_base_url_trailing_slash_tolerated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    result = _probe(handler, base_url="https://x.test/v1/")
    assert result.ok is True
    assert result.error is None
