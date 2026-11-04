"""Checkpoint prompt endpoint tests: static shape, no-key serving, registration.

Offline — the endpoint reads no settings, DB, or network; the repo-root .env
is blocked via a Settings(_env_file=None) factory so cases can never pick up
the developer's live key. Mirrors `test_health.py` isolation.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.prompts import CHECKPOINT_PROMPT
from app.core.config import Settings, get_settings
from app.main import create_app

MARKERS = (
    "Work performed",
    "Problems encountered",
    "Decisions and reasoning",
    "Accomplishments and skills demonstrated",
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "prompts_api.db"))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client() -> TestClient:
    return TestClient(create_app())


def test_checkpoint_returns_prompt_text() -> None:
    response = _client().get("/api/v1/prompts/checkpoint")
    assert response.status_code == 200
    assert response.json() == {"prompt": CHECKPOINT_PROMPT}
    assert CHECKPOINT_PROMPT.strip() != ""


def test_checkpoint_is_static_and_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    first = _client().get("/api/v1/prompts/checkpoint")
    second = _client().get("/api/v1/prompts/checkpoint")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text


def test_checkpoint_in_openapi() -> None:
    paths = _client().get("/openapi.json").json()["paths"]
    assert list(paths["/api/v1/prompts/checkpoint"]) == ["get"]


def test_checkpoint_covers_f9_sections() -> None:
    for marker in MARKERS:
        assert marker in CHECKPOINT_PROMPT, marker
