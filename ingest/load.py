"""Raw landing load: data/raw/ -> Postgres raw.* tables (db/schema.sql).

No network calls. Reads every cached response already on disk, plus the two
routing CSVs in data/reference/generated/, and truncates then inserts each
of the nine raw tables, so a rerun is idempotent and costs nothing beyond a
database round trip. Requires db/schema.sql to already be applied.

Everything lands as text; casting happens later in dbt staging. Each table
also gets source_file (the cache filename) and, where the source is JSON,
payload (the full source record) so staging can always fall back to the
untouched original. The routing CSVs have no payload: every CSV column is
named.

Comtrade and every PortWatch table are key checked: every record must
carry every key mapped to a column, or the load raises. Keys present in the data but not mapped are printed; they are
still preserved in payload.

For the two Census tables, the source header repeats I_COMMODITY (the
filter parameter Census echoes back). dict(zip(header, row)) would collapse
that duplicate key and silently drop the echoed value, so payload is built
positionally instead: a JSON array of [header, value] pairs, and every named
column is read by its fixed position in the row, not by header name.

Usage: .venv/bin/python -m ingest.load
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.census import expected_header  # noqa: E402
from ingest.config import require_postgres_dsn  # noqa: E402
from ingest.portwatch import (  # noqa: E402
    CHOKEPOINTS_CACHE_FILE,
    DISRUPTIONS_CACHE_PREFIX,
    PORTS_CACHE_PREFIX,
    TRANSITS_CACHE_PREFIX,
    read_cached_page_features,
    validate_chokepoints_payload,
)
from ingest.routing import (  # noqa: E402
    MATRIX_HEADER,
    ROUTES_HEADER,
    ROUTES_PATH,
    ROUTING_MATRIX_PATH,
)

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


def _check_keys(label: str, records: list[dict], mapped: list[str]) -> list[str]:
    """Raise if any record lacks a mapped key. Return the sorted keys seen in
    the data but not mapped (preserved in payload, reported, not raised)."""
    mapped_set = set(mapped)
    missing: dict[str, int] = {}
    seen: set[str] = set()
    for record in records:
        seen.update(record)
        for key in mapped_set.difference(record):
            missing[key] = missing.get(key, 0) + 1
    if missing:
        detail = ", ".join(f"{k} ({n} records)" for k, n in sorted(missing.items()))
        raise RuntimeError(
            f"{label}: mapped key(s) missing from the data: {detail}. A missing "
            "key would load as NULL; reconcile the column map before loading."
        )
    return sorted(seen - mapped_set)


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


def load_comtrade_imports(cur: psycopg.Cursor) -> tuple[int, list[str]]:
    records = []
    for path in sorted(CACHE_DIR.glob("comtrade_final_C_A_*.json")):
        payload = json.loads(path.read_text())
        records.extend((path.name, record) for record in payload.get("data", []))
    unmapped = _check_keys("comtrade_imports", [r for _, r in records], _COMTRADE_JSON_KEYS)
    rows = []
    for source_file, record in records:
        values = [_text(record[key]) for key in _COMTRADE_JSON_KEYS]
        values.append(_text(record["classificationCode"]))  # hs_version
        values.append(source_file)
        values.append(json.dumps(record))  # payload
        rows.append(values)
    return _insert(cur, "comtrade_imports", _COMTRADE_COLUMNS, rows), unmapped


# ---------------------------------------------------------------------------
# census_hs_annual, census_porths_vessel
# ---------------------------------------------------------------------------

# Named columns, by fixed position in the header that
# ingest.census.expected_header() returns for each pull.
_CENSUS_HS_ANNUAL_COLUMNS = [
    "i_commodity", "cty_code", "cty_name", "summary_lvl", "gen_val_yr",
    "air_val_yr", "ves_val_yr", "cnt_val_yr", "comm_lvl", "i_commodity_echo", "time",
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
    if len(expected_header) != len(named_columns):
        raise RuntimeError(
            f"raw.{table}: expected header has {len(expected_header)} fields "
            f"but {len(named_columns)} named columns are mapped."
        )
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
        expected_header("hs"),
        _CENSUS_HS_ANNUAL_COLUMNS,
    )


def load_census_porths_vessel(cur: psycopg.Cursor) -> int:
    return _load_census_table(
        cur,
        "census_porths_vessel",
        "census_porths_vessel_*.json",
        expected_header("porths_vessel"),
        _CENSUS_PORTHS_VESSEL_COLUMNS,
    )


# ---------------------------------------------------------------------------
# portwatch_chokepoint_transits, portwatch_chokepoints, portwatch_ports,
# portwatch_disruptions
# ---------------------------------------------------------------------------

# (ArcGIS attribute key, raw column), in db/schema.sql column order.
_PORTWATCH_TRANSITS_MAP = [
    (col, col)
    for col in (
        "portid", "portname", "date", "n_container", "n_dry_bulk",
        "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total",
        "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
        "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
    )
]

_PORTWATCH_CHOKEPOINTS_MAP = [(col, col) for col in ("portid", "portname", "lat", "lon")]

_PORTWATCH_PORTS_MAP = [
    ("portid", "portid"), ("portname", "portname"), ("country", "country"),
    ("ISO3", "iso3"), ("continent", "continent"), ("fullname", "fullname"),
    ("lat", "lat"), ("lon", "lon"),
    ("vessel_count_total", "vessel_count_total"),
    ("vessel_count_container", "vessel_count_container"),
    ("vessel_count_dry_bulk", "vessel_count_dry_bulk"),
    ("vessel_count_general_cargo", "vessel_count_general_cargo"),
    ("vessel_count_RoRo", "vessel_count_roro"),
    ("vessel_count_tanker", "vessel_count_tanker"),
    ("industry_top1", "industry_top1"), ("industry_top2", "industry_top2"),
    ("industry_top3", "industry_top3"),
    ("share_country_maritime_import", "share_country_maritime_import"),
    ("share_country_maritime_export", "share_country_maritime_export"),
    ("LOCODE", "locode"), ("pageid", "pageid"),
    ("countrynoaccents", "countrynoaccents"), ("ObjectId", "objectid"),
]

_PORTWATCH_DISRUPTIONS_MAP = [
    ("eventid", "eventid"), ("eventtype", "eventtype"),
    ("eventname", "eventname"), ("htmlname", "htmlname"),
    ("htmldescription", "htmldescription"), ("alertlevel", "alertlevel"),
    ("country", "country"), ("fromdate", "fromdate"), ("year", "year"),
    ("todate", "todate"), ("severitytext", "severitytext"), ("lat", "lat"),
    ("long", "long"), ("editdate", "editdate"),
    ("affectedports", "affectedports"), ("n_affectedports", "n_affectedports"),
    ("affectedpopulation", "affectedpopulation"), ("pageid", "pageid"),
    ("ObjectId", "objectid"), ("Shape__Area", "shape_area"),
    ("Shape__Length", "shape_length"),
]


def _load_portwatch_features(
    cur: psycopg.Cursor,
    table: str,
    page_features: list[tuple[str, dict]],
    column_map: list[tuple[str, str]],
    payload_attributes_only: bool,
) -> tuple[int, list[str]]:
    """page_features are (cache filename, ArcGIS feature) pairs, already
    validated by the caller. payload is either the attributes alone
    (transits, chokepoints: unchanged from before) or the full feature,
    attributes and geometry (ports, disruptions)."""
    keys = [key for key, _ in column_map]
    unmapped = _check_keys(table, [f["attributes"] for _, f in page_features], keys)
    rows = []
    for source_file, feature in page_features:
        attrs = feature["attributes"]
        values = [_text(attrs[key]) for key in keys]
        values.append(source_file)
        values.append(json.dumps(attrs if payload_attributes_only else feature))
        rows.append(values)
    columns = [col for _, col in column_map] + ["source_file", "payload"]
    return _insert(cur, table, columns, rows), unmapped


def load_portwatch_chokepoint_transits(cur: psycopg.Cursor) -> tuple[int, list[str]]:
    # portwatch_chokepoint5_offset*.json are the single-chokepoint pagination
    # test files from the removed verification_round1.py spike, a subset already
    # covered here; the TRANSITS_CACHE_PREFIX pages never include them.
    return _load_portwatch_features(
        cur,
        "portwatch_chokepoint_transits",
        read_cached_page_features(TRANSITS_CACHE_PREFIX),
        _PORTWATCH_TRANSITS_MAP,
        payload_attributes_only=True,
    )


def load_portwatch_chokepoints(cur: psycopg.Cursor) -> tuple[int, list[str]]:
    payload = json.loads(CHOKEPOINTS_CACHE_FILE.read_text())
    validate_chokepoints_payload(payload)
    return _load_portwatch_features(
        cur,
        "portwatch_chokepoints",
        [(CHOKEPOINTS_CACHE_FILE.name, f) for f in payload["features"]],
        _PORTWATCH_CHOKEPOINTS_MAP,
        payload_attributes_only=True,
    )


def load_portwatch_ports(cur: psycopg.Cursor) -> tuple[int, list[str]]:
    return _load_portwatch_features(
        cur,
        "portwatch_ports",
        read_cached_page_features(PORTS_CACHE_PREFIX),
        _PORTWATCH_PORTS_MAP,
        payload_attributes_only=False,
    )


def load_portwatch_disruptions(cur: psycopg.Cursor) -> tuple[int, list[str]]:
    return _load_portwatch_features(
        cur,
        "portwatch_disruptions",
        read_cached_page_features(DISRUPTIONS_CACHE_PREFIX),
        _PORTWATCH_DISRUPTIONS_MAP,
        payload_attributes_only=False,
    )


# ---------------------------------------------------------------------------
# routes, routing_matrix
# ---------------------------------------------------------------------------


def _load_csv(cur: psycopg.Cursor, table: str, path: Path, header: tuple[str, ...]) -> int:
    """Header must equal the one ingest/routing.py writes; columns keep the
    CSV names. Empty cells load as empty strings, not NULL, as written."""
    with path.open(newline="") as f:
        reader = csv.reader(f)
        file_header = next(reader, None)
        if tuple(file_header or ()) != header:
            raise RuntimeError(f"{path.name}: header {file_header} does not equal expected {list(header)}.")
        rows = []
        for n, record in enumerate(reader, start=2):
            if len(record) != len(header):
                raise RuntimeError(f"{path.name}: line {n} has {len(record)} values, header has {len(header)}.")
            rows.append(record + [path.name])
    return _insert(cur, table, list(header) + ["source_file"], rows)


def load_routes(cur: psycopg.Cursor) -> int:
    return _load_csv(cur, "routes", ROUTES_PATH, ROUTES_HEADER)


def load_routing_matrix(cur: psycopg.Cursor) -> int:
    return _load_csv(cur, "routing_matrix", ROUTING_MATRIX_PATH, MATRIX_HEADER)


def main() -> None:
    unmapped: dict[str, list[str]] = {}
    with psycopg.connect(require_postgres_dsn()) as conn, conn.cursor() as cur:
        counts = {}
        counts["raw.comtrade_imports"], unmapped["raw.comtrade_imports"] = load_comtrade_imports(cur)
        counts["raw.census_hs_annual"] = load_census_hs_annual(cur)
        counts["raw.census_porths_vessel"] = load_census_porths_vessel(cur)
        counts["raw.portwatch_chokepoint_transits"], unmapped["raw.portwatch_chokepoint_transits"] = (
            load_portwatch_chokepoint_transits(cur)
        )
        counts["raw.portwatch_chokepoints"], unmapped["raw.portwatch_chokepoints"] = (
            load_portwatch_chokepoints(cur)
        )
        counts["raw.portwatch_ports"], unmapped["raw.portwatch_ports"] = load_portwatch_ports(cur)
        counts["raw.portwatch_disruptions"], unmapped["raw.portwatch_disruptions"] = (
            load_portwatch_disruptions(cur)
        )
        counts["raw.routes"] = load_routes(cur)
        counts["raw.routing_matrix"] = load_routing_matrix(cur)
    for table, count in counts.items():
        print(f"{table}: {count} rows")
    for table, keys in unmapped.items():
        print(f"{table}: unmapped keys (kept in payload): {', '.join(keys) if keys else 'none'}")


if __name__ == "__main__":
    main()
