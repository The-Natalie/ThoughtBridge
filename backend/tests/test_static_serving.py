"""Static-serving tests: opt-in SPA mount, mount order, absent-by-default, fail-fast.

Offline suite comparison in test_app_boot covers unconfigured boot; these
tests exercise the STATIC_DIR branch of create_app() behind an isolated
Settings factory (never the repo-root .env) with the Meta probe stubbed.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.meta_client import ProbeResult
from app.db.connection import init_db
from app.main import create_app

INDEX_MARKER = "ThoughtBridge static probe"


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
        "STATIC_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.api.health.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


async def _probe_ok(key: str, model: str, **kwargs: Any) -> ProbeResult:
    return ProbeResult(True, None, 200)


def _static_dir(tmp_path: Path) -> str:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(f"<html><body>{INDEX_MARKER}</body></html>")
    (root / "assets" / "app.js").write_text("console.log('static probe');")
    return str(root)


def _healthy_db(tmp_path: Path) -> str:
    path = tmp_path / "healthy.db"
    init_db(path)
    return str(path)


def test_serves_index_at_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STATIC_DIR", _static_dir(tmp_path))
    monkeypatch.setenv("DATABASE_PATH", _healthy_db(tmp_path))
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert INDEX_MARKER in response.text


def test_serves_nested_asset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STATIC_DIR", _static_dir(tmp_path))
    monkeypatch.setenv("DATABASE_PATH", _healthy_db(tmp_path))
    client = TestClient(create_app())
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "static probe" in response.text


def test_api_docs_and_health_unaffected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.api.health.check_meta_reachability", _probe_ok)
    monkeypatch.setenv("STATIC_DIR", _static_dir(tmp_path))
    monkeypatch.setenv("DATABASE_PATH", _healthy_db(tmp_path))
    monkeypatch.setenv("MODEL_API_KEY", "dummy")
    monkeypatch.setenv("META_MODEL", "muse-spark-1.3")
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
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


def test_root_404_without_static_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_PATH", _healthy_db(tmp_path))
    client = TestClient(create_app())
    assert client.get("/").status_code == 404


def test_set_but_missing_static_dir_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("DATABASE_PATH", _healthy_db(tmp_path))
    with pytest.raises(RuntimeError, match="STATIC_DIR does not exist"):
        create_app()
