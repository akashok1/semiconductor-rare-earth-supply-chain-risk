"""Environment configuration and source URLs, in one place for all of ingest/.

Every ingest script obtains credentials through the accessors here, never by
reading ``os.environ`` or ``.env`` directly, and every source URL lives here
as a module constant -- no other file in ingest/ defines one. Importing this
module must never raise: each accessor is a lazy, fail-fast check called only
by the script that actually needs that credential, so a script that only
touches Comtrade is never blocked by a missing Census key (see
PROJECT_BRIEF.md section 5, "Operational trap": a dead key must never produce
a silent empty ingest -- it must fail loudly, but only when actually used).
"""

from __future__ import annotations

import os

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


def require_comtrade_api_key() -> str:
    """Fail-fast accessor for COMTRADE_API_KEY. Not validated at import time:
    see module docstring."""
    return _require_env("COMTRADE_API_KEY")


def require_census_api_key() -> str:
    """Fail-fast accessor for CENSUS_API_KEY, mirroring
    require_comtrade_api_key. Deliberately not validated at import time:
    a script that only touches Comtrade must never be blocked by a missing
    Census key."""
    return _require_env("CENSUS_API_KEY")


def require_postgres_dsn() -> str:
    """Fail-fast accessor for a psycopg connection string, built from the same
    POSTGRES_* variables docker-compose.yml uses. Deliberately not validated
    at import time, for the same reason as require_census_api_key: only
    scripts that actually touch Postgres (currently just ``ingest/load.py``)
    should be forced to have these variables set.
    """
    user = _require_env("POSTGRES_USER")
    password = _require_env("POSTGRES_PASSWORD")
    dbname = _require_env("POSTGRES_DB")
    host = os.environ.get("POSTGRES_HOST", "").strip() or "localhost"
    # No default: the project Postgres runs on 5433 (docker-compose.yml), and
    # a system Postgres already owns 5432 on this machine. Defaulting to
    # either port risks silently connecting to the wrong database, so a
    # missing POSTGRES_PORT must fail instead of guessing.
    port = _require_env("POSTGRES_PORT")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


# ---------------------------------------------------------------------------
# Project year range, inclusive. The one range every annual pull covers.
# ---------------------------------------------------------------------------

YEAR_START = 2018
YEAR_END = 2025


# ---------------------------------------------------------------------------
# Source URLs. No other file in ingest/ defines one.
# ---------------------------------------------------------------------------

# UN Comtrade: annual final trade data, all classification vintages.
COMTRADE_DATA_BASE = "https://comtradeapi.un.org/data/v1"

# US Census international trade API.
CENSUS_IMPORTS_HS_URL = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
CENSUS_IMPORTS_PORTHS_URL = "https://api.census.gov/data/timeseries/intltrade/imports/porths"

# Official Census/CBP Schedule D port and district code list.
CENSUS_SCHEDULE_D_PORTS_URL = "https://www.census.gov/foreign-trade/schedules/d/dist2.txt"

# UN Stats HS2022-to-HS2017 conversion and correlation workbook.
UN_HS_CORRELATION_URL = (
    "https://unstats.un.org/unsd/classifications/Econ/tables/"
    "HS2022toHS2017ConversionAndCorrelationTables.xlsx"
)

# IMF PortWatch, ArcGIS FeatureServer, no key. Each service is
# {PORTWATCH_ARCGIS_BASE}/{service}/FeatureServer/{layer}/query.
PORTWATCH_ARCGIS_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTWATCH_CHOKEPOINTS_SERVICE = "PortWatch_chokepoints_database"
PORTWATCH_DAILY_TRANSITS_SERVICE = "Daily_Chokepoints_Data"
PORTWATCH_PORTS_SERVICE = "PortWatch_ports_database"
PORTWATCH_DISRUPTIONS_SERVICE = "portwatch_disruptions_database"
