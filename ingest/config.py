"""Environment configuration, loaded once and validated before any network call.

Every ingest or analysis script must obtain credentials through ``CONFIG`` here,
never by reading ``os.environ`` or ``.env`` directly. Importing this module
raises immediately if a required variable is missing or empty, so a bad
environment fails at start-up rather than after a partial run (see
PROJECT_BRIEF.md section 5, "Operational trap": a dead key must never produce
a silent empty ingest).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or empty."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is missing or empty. Set it in .env (see .env.example) "
            "before running any ingest or analysis script."
        )
    return value


@dataclass(frozen=True)
class Config:
    comtrade_api_key: str


CONFIG = Config(comtrade_api_key=_require_env("COMTRADE_API_KEY"))


def require_census_api_key() -> str:
    """Fail-fast accessor for CENSUS_API_KEY, mirroring CONFIG.comtrade_api_key.

    Deliberately not folded into ``CONFIG``: that object is validated eagerly
    at import time, and every script that imports this module (including ones
    that only touch Comtrade) would then be forced to have a Census key too.
    Scripts that actually need the Census key call this explicitly instead.
    """
    return _require_env("CENSUS_API_KEY")


def require_postgres_dsn() -> str:
    """Fail-fast accessor for a psycopg connection string, built from the same
    POSTGRES_* variables docker-compose.yml uses. Deliberately not folded into
    ``CONFIG`` for the same reason as ``require_census_api_key``: only scripts
    that actually touch Postgres (currently just ``ingest/load.py``) should be
    forced to have these variables set.
    """
    user = _require_env("POSTGRES_USER")
    password = _require_env("POSTGRES_PASSWORD")
    dbname = _require_env("POSTGRES_DB")
    host = os.environ.get("POSTGRES_HOST", "").strip() or "localhost"
    port = os.environ.get("POSTGRES_PORT", "").strip() or "5432"
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"
