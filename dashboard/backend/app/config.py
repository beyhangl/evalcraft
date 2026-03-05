"""Application settings via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


def _default_secret() -> str:
    """Require EVALCRAFT_SECRET_KEY in production, use random key for dev."""
    return os.environ.get("EVALCRAFT_SECRET_KEY", os.urandom(32).hex())


class Settings(BaseSettings):
    model_config = {"env_prefix": "EVALCRAFT_", "env_file": ".env"}

    # App
    app_name: str = "Evalcraft Dashboard"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://evalcraft:evalcraft@localhost:5432/evalcraft"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = _default_secret()
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
