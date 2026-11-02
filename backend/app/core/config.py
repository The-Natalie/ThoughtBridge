"""Application settings — loads the repo-root .env (see .env.example for the surface)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    model_api_key: SecretStr = SecretStr("")
    # Recorded at CHECKPOINT 1 — must equal core.meta_client.DEFAULT_META_MODEL (drift-guarded by test)
    meta_model: str = "muse-spark-1.3"
    database_path: str = "./data/thoughtbridge.db"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    max_upload_mb: int = 10
    max_artifact_chars: int = 500_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
