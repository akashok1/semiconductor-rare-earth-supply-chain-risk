"""Raw landing load: data/raw/ -> Postgres raw.* tables (db/schema.sql).

No network calls. Reads every cached response already on disk and truncates
then inserts each of the six raw tables, so a rerun is idempotent and costs
nothing beyond a database round trip. Requires db/schema.sql to already be
applied.

Everything lands as text; casting happens later in dbt staging. Each table
also gets source_file (the cache filename) and payload (the full source row,
as JSON) so staging can always fall back to the untouched original.

For the three Census tables, the source header repeats I_COMMODITY (the
filter parameter Census echoes back). dict(zip(header, row)) would collapse
that duplicate key and silently drop the echoed value, so payload is built
positionally instead: a JSON array of [header, value] pairs, and every named
column is read by its fixed position in the row, not by header name.

Usage: .venv/bin/python -m ingest.load
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import require_postgres_dsn  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"


def _text(value: Any) -> str | None:
    """Cast a JSON-decoded scalar to text. Every raw column is text; no
    casting happens here or anywhere in this module."""
    return None if value is None else str(value)


def _insert(cur: psycopg.Cursor, table: str, columns: list[str], rows: list[list]) -> int:
    cur.execute(f"TRUNCATE TABLE raw.{table}")
    if rows:
        placeholders = ", ".join(["%s"] * len(columns))
        cur.executemany(
            f"INSERT INTO raw.{table} ({', '.join(columns)}) VALUES ({placeholders})",
            rows,
        )
    return len(rows)


# ---------------------------------------------------------------------------
# comtrade_imports
# ---------------------------------------------------------------------------

# Order matches db/schema.sql, source columns only (hs_version, source_file,
# payload are appended separately below).
_COMTRADE_JSON_KEYS = [
    "typeCode", "freqCode", "refPeriodId", "refYear", "refMonth", "period",
    "reporterCode", "reporterISO", "reporterDesc", "flowCode", "flowDesc",
    "partnerCode", "partnerISO", "partnerDesc", "partner2Code",
    "partner2ISO", "partner2Desc", "classificationCode",
    "classificationSearchCode", "isOriginalClassification", "cmdCode",
    "cmdDesc", "aggrLevel", "isLeaf", "customsCode", "customsDesc",
    "mosCode", "motCode", "motDesc", "qtyUnitCode", "qtyUnitAbbr", "qty",
    "isQtyEstimated", "altQtyUnitCode", "altQtyUnitAbbr", "altQty",
    "isAltQtyEstimated", "netWgt", "isNetWgtEstimated", "grossWgt",
    "isGrossWgtEstimated", "cifvalue", "fobvalue", "primaryValue",
    "legacyEstimationFlag", "isReported", "isAggregate",
]

_COMTRADE_COLUMNS = [
    "type_code", "freq_code", "ref_period_id", "ref_year", "ref_month",
    "period", "reporter_code", "reporter_iso", "reporter_desc", "flow_code",
    "flow_desc", "partner_code", "partner_iso", "partner_desc",
    "partner2_code", "partner2_iso", "partner2_desc", "classification_code",
    "classification_search_code", "is_original_classification", "cmd_code",
    "cmd_desc", "aggr_level", "is_leaf", "customs_code", "customs_desc",
    "mos_code", "mot_code", "mot_desc", "qty_unit_code", "qty_unit_abbr",
    "qty", "is_qty_estimated", "alt_qty_unit_code", "alt_qty_unit_abbr",
    "alt_qty", "is_alt_qty_estimated", "net_wgt", "is_net_wgt_estimated",
    "gross_wgt", "is_gross_wgt_estimated", "cifvalue", "fobvalue",
    "primary_value", "legacy_estimation_flag", "is_reported", "is_aggregate",
    "hs_version", "source_file", "payload",
]


def load_comtrade_imports(cur: psycopg.Cursor) -> int:
    rows = []
    for path in sorted(CACHE_DIR.glob("comtrade_final_C_A_*.json")):
        payload = json.loads(path.read_text())
        for record in payload.get("data", []):
            values = [_text(record.get(key)) for key in _COMTRADE_JSON_KEYS]
            values.append(_text(record.get("classificationCode")))  # hs_version
            values.append(path.name)  # source_file
            values.append(json.dumps(record))  # payload
            rows.append(values)
    return _insert(cur, "comtrade_imports", _COMTRADE_COLUMNS, rows)


# ---------------------------------------------------------------------------
# census_hs_annual, census_porths_annual, census_porths_vessel
# ---------------------------------------------------------------------------

_CENSUS_HS_ANNUAL_HEADER = [
    "I_COMMODITY", "CTY_CODE", "CTY_NAME", "SUMMARY_LVL", "GEN_VAL_YR",
    "AIR_VAL_YR", "VES_VAL_YR", "CNT_VAL_YR", "COMM_LVL", "I_COMMODITY", "time",
]
_CENSUS_HS_ANNUAL_COLUMNS = [
    "i_commodity", "cty_code", "cty_name", "summary_lvl", "gen_val_yr",
    "air_val_yr", "ves_val_yr", "cnt_val_yr", "comm_lvl", "i_commodity_echo", "time",
]

_CENSUS_PORTHS_ANNUAL_HEADER = [
    "I_COMMODITY", "PORT", "PORT_NAME", "SUMMARY_LVL", "GEN_VAL_YR",
    "COMM_LVL", "I_COMMODITY", "time",
]
_CENSUS_PORTHS_ANNUAL_COLUMNS = [
    "i_commodity", "port", "port_name", "summary_lvl", "gen_val_yr",
    "comm_lvl", "i_commodity_echo", "time",
]

_CENSUS_PORTHS_VESSEL_HEADER = [
    "I_COMMODITY", "PORT", "PORT_NAME", "SUMMARY_LVL", "GEN_VAL_YR",
    "VES_VAL_YR", "COMM_LVL", "I_COMMODITY", "time",
]
_CENSUS_PORTHS_VESSEL_COLUMNS = [
    "i_commodity", "port", "port_name", "summary_lvl", "gen_val_yr",
    "ves_val_yr", "comm_lvl", "i_commodity_echo", "time",
]


def _load_census_table(
    cur: psycopg.Cursor,
    table: str,
    glob_pattern: str,
    expected_header: list[str],
    named_columns: list[str],
) -> int:
    rows = []
    for path in sorted(CACHE_DIR.glob(glob_pattern)):
        payload = json.loads(path.read_text())
        header, *data_rows = payload
        if header != expected_header:
            raise RuntimeError(
                f"{path.name}: header {header} does not match the expected "
                f"raw.{table} header {expected_header}. Named columns below "
                "are read by fixed position, not by header name, so a "
                "changed header must be reconciled before loading."
            )
        for record in data_rows:
            values = [_text(v) for v in record[: len(named_columns)]]
            values.append(path.name)  # source_file
            values.append(json.dumps(list(zip(header, record))))  # payload
            rows.append(values)
    columns = named_columns + ["source_file", "payload"]
    return _insert(cur, table, columns, rows)


def load_census_hs_annual(cur: psycopg.Cursor) -> int:
    return _load_census_table(
        cur,
        "census_hs_annual",
        "census_hs_annual_*.json",
        _CENSUS_HS_ANNUAL_HEADER,
        _CENSUS_HS_ANNUAL_COLUMNS,
    )


def load_census_porths_annual(cur: psycopg.Cursor) -> int:
    return _load_census_table(
        cur,
        "census_porths_annual",
        "census_porths_annual_*.json",
        _CENSUS_PORTHS_ANNUAL_HEADER,
        _CENSUS_PORTHS_ANNUAL_COLUMNS,
    )


def load_census_porths_vessel(cur: psycopg.Cursor) -> int:
    return _load_census_table(
        cur,
        "census_porths_vessel",
        "census_porths_vessel_*.json",
        _CENSUS_PORTHS_VESSEL_HEADER,
        _CENSUS_PORTHS_VESSEL_COLUMNS,
    )


# ---------------------------------------------------------------------------
# portwatch_chokepoint_transits, portwatch_chokepoints
# ---------------------------------------------------------------------------

_PORTWATCH_TRANSIT_COLUMNS = [
    "portid", "portname", "date", "n_container", "n_dry_bulk",
    "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total",
    "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
    "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
]

_PORTWATCH_CHOKEPOINTS_COLUMNS = ["portid", "portname", "lat", "lon"]


def _load_arcgis_features(
    cur: psycopg.Cursor, table: str, glob_pattern: str, named_columns: list[str]
) -> int:
    rows = []
    for path in sorted(CACHE_DIR.glob(glob_pattern)):
        payload = json.loads(path.read_text())
        for feature in payload.get("features", []):
            attrs = feature["attributes"]
            values = [_text(attrs.get(col)) for col in named_columns]
            values.append(path.name)  # source_file
            values.append(json.dumps(attrs))  # payload
            rows.append(values)
    columns = named_columns + ["source_file", "payload"]
    return _insert(cur, table, columns, rows)


def load_portwatch_chokepoint_transits(cur: psycopg.Cursor) -> int:
    # portwatch_chokepoint5_offset*.json are the single-chokepoint pagination
    # test files from analysis/verification_round1.py, a subset already
    # covered here; loading them too would double-count those rows.
    return _load_arcgis_features(
        cur, "portwatch_chokepoint_transits", "portwatch_full_offset*.json", _PORTWATCH_TRANSIT_COLUMNS
    )


def load_portwatch_chokepoints(cur: psycopg.Cursor) -> int:
    return _load_arcgis_features(
        cur, "portwatch_chokepoints", "portwatch_chokepoints_geometry.json", _PORTWATCH_CHOKEPOINTS_COLUMNS
    )


def main() -> None:
    with psycopg.connect(require_postgres_dsn()) as conn, conn.cursor() as cur:
        counts = {
            "raw.comtrade_imports": load_comtrade_imports(cur),
            "raw.census_hs_annual": load_census_hs_annual(cur),
            "raw.census_porths_annual": load_census_porths_annual(cur),
            "raw.census_porths_vessel": load_census_porths_vessel(cur),
            "raw.portwatch_chokepoint_transits": load_portwatch_chokepoint_transits(cur),
            "raw.portwatch_chokepoints": load_portwatch_chokepoints(cur),
        }
    for table, count in counts.items():
        print(f"{table}: {count} rows")


if __name__ == "__main__":
    main()
