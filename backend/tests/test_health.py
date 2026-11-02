"""Health endpoint tests: 200/503 shapes, short-circuits, liveness, key hygiene.

Offline — the Meta probe is stubbed or the key omitted in every test, and the
repo-root .env is blocked via a Settings(_env_file=None) factory so cases can
never pick up the developer's live key.
"""

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.meta_client import DEFAULT_META_MODEL, ProbeResult
from app.db.connection import check_readable, init_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr("app.api.health.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def _healthy_db(tmp_path: Path) -> str:
    path = tmp_path / "healthy.db"
    init_db(path)
    return str(path)


def _assert_no_db_files(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        assert not os.path.exists(path + suffix), path + suffix


async def _probe_ok(key: str, model: str, **kwargs: Any) -> ProbeResult:
    assert model == "muse-spark-1.3"
    return ProbeResult(True, None, 200)


async def _probe_must_not_run(key: str, model: str, **kwargs: Any) -> ProbeResult:
    raise AssertionError("must not be called")


def test_healthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_ok)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="dummy",
        META_MODEL="muse-spark-1.3",
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": True,
        "meta_api": True,
        "model": "muse-spark-1.3",
        "db_error": None,
        "meta_error": None,
    }


def test_meta_down_reported_honestly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _probe_down(key: str, model: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(False, "Meta API models probe: HTTP 401: nope", 401)

    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_down)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="dummy",
        META_MODEL="muse-spark-1.3",
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["meta_api"] is False
    assert "401" in body["meta_error"]
    assert body["db"] is True


@pytest.mark.parametrize("mode", ["unset", "empty"])
def test_missing_key_skips_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_must_not_run)
    if mode == "unset":
        monkeypatch.delenv("MODEL_API_KEY", raising=False)
        client = _client(
            monkeypatch,
            DATABASE_PATH=_healthy_db(tmp_path),
            META_MODEL="muse-spark-1.3",
        )
    else:
        client = _client(
            monkeypatch,
            DATABASE_PATH=_healthy_db(tmp_path),
            MODEL_API_KEY="",
            META_MODEL="muse-spark-1.3",
        )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["meta_api"] is False
    assert "not configured" in body["meta_error"]


def test_empty_model_falls_back_to_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _probe_default(key: str, model: str, **kwargs: Any) -> ProbeResult:
        assert model == DEFAULT_META_MODEL
        return ProbeResult(True, None, 200)

    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_default)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="dummy",
        META_MODEL="",
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["model"] == DEFAULT_META_MODEL


def test_check_readable_missing_file() -> None:
    path = f"/tmp/tb_health_direct_missing_{os.getpid()}.db"
    _assert_no_db_files(path)
    result = check_readable(path)
    assert result.ok is False
    assert result.error
    _assert_no_db_files(path)


def test_missing_db_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/tmp/tb_health_missing_{os.getpid()}.db"
    _assert_no_db_files(path)
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_ok)
    client = _client(
        monkeypatch,
        DATABASE_PATH=path,
        MODEL_API_KEY="dummy",
        META_MODEL="muse-spark-1.3",
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] is False
    assert body["db_error"]
    _assert_no_db_files(path)


def test_liveness_is_lightweight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_must_not_run)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="dummy",
        META_MODEL="muse-spark-1.3",
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "db_error": None}
    assert "meta_api" not in response.json()


def test_liveness_db_down_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/tmp/tb_health_liveness_missing_{os.getpid()}.db"
    _assert_no_db_files(path)
    client = _client(monkeypatch, DATABASE_PATH=path)
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] is False
    _assert_no_db_files(path)


def test_key_never_in_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _probe_down(key: str, model: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(False, "Meta API models probe: HTTP 401: nope", 401)

    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_down)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="canary-health-999",
        META_MODEL="muse-spark-1.3",
    )
    response = client.get("/api/v1/health")
    assert "canary-health-999" not in response.text


def test_required_keys_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_ok)
    client = _client(
        monkeypatch,
        DATABASE_PATH=_healthy_db(tmp_path),
        MODEL_API_KEY="dummy",
        META_MODEL="muse-spark-1.3",
    )
    assert {"status", "db", "meta_api"} <= set(client.get("/api/v1/health").json())
    assert set(client.get("/health").json()) == {"status", "db", "db_error"}
