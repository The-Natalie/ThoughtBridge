"""Config tests: defaults, overrides, and secret hygiene. Never touches the real .env."""

import pytest

from app.core.config import Settings, get_settings


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


def test_defaults_resolve_without_env_file() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_path == "./data/thoughtbridge.db"
    assert settings.max_upload_mb == 10
    assert settings.max_artifact_chars == 500_000
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"


def test_env_overrides_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", "/tmp/x.db")
    monkeypatch.setenv("MAX_UPLOAD_MB", "25")
    settings = Settings(_env_file=None)
    assert settings.database_path == "/tmp/x.db"
    assert settings.max_upload_mb == 25


def test_api_key_never_leaks_into_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "dummy-key-123")
    settings = Settings(_env_file=None)
    assert "dummy-key-123" not in repr(settings)
    assert settings.model_api_key.get_secret_value() == "dummy-key-123"
