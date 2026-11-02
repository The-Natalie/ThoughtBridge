"""Meta client tests: recorded model ID, probe mapping, truncation, key hygiene.

Every probe test is offline — HTTP is stubbed via httpx.MockTransport, never
a real AsyncClient.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.meta_client import (
    DEFAULT_META_MODEL,
    MAX_ERROR_CHARS,
    QA_MAX_TOKENS,
    MetaAPIError,
    ProbeResult,
    chat_completion,
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


CHAT_MESSAGES = [{"role": "user", "content": "q"}]


def _chat(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> str:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    params: dict[str, Any] = {"api_key": CANARY, "messages": CHAT_MESSAGES, "client": client}
    params.update(kwargs)
    return asyncio.run(chat_completion(**params))


def test_chat_200_returns_content_and_sends_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {CANARY}"
        sent = json.loads(request.content.decode())
        assert sent["model"] == MODEL
        assert sent["messages"] == CHAT_MESSAGES
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["max_tokens"] == QA_MAX_TOKENS
        return httpx.Response(200, json={"choices": [{"message": {"content": "out"}}]})

    assert _chat(handler) == "out"


def test_chat_401_raises_with_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized nope")

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code == 401
    assert "401" in str(exc_info.value)
    assert CANARY not in str(exc_info.value)


def test_chat_500_body_truncated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="x" * 1000)

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code == 500
    assert CANARY not in str(exc_info.value)
    assert len(exc_info.value.detail) <= len("HTTP 500: ") + MAX_ERROR_CHARS


def test_chat_timeout_has_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code is None
    assert "timed" in str(exc_info.value).lower()


def test_chat_connection_error_has_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code is None
    assert CANARY not in str(exc_info.value)


def test_chat_200_bad_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json{{{", headers={"content-type": "text/plain"})

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code == 200


def test_chat_200_empty_choices_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code == 200


def test_chat_200_empty_content_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    with pytest.raises(MetaAPIError) as exc_info:
        _chat(handler)
    assert exc_info.value.status_code == 200


def test_chat_base_url_trailing_slash_tolerated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    assert _chat(handler, base_url="https://x.test/v1/") == "ok"
