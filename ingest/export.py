"""Mart export: Postgres analytics.fct_* -> exports/*.csv for Tableau.

Dumps each mart table to one CSV with COPY ... TO STDOUT (header row). No
calculation happens here: every figure is computed in dbt. The only
transformations are presentational: ratio and share columns are rounded to
ROUND_DECIMALS (dollar values and integers are left as they are), and
fct_exposure omits its per code-year diagnostics, which repeat on every row
and are exported once per code-year in fct_exposure_summary. Rows are
ordered by each mart's grain so reruns produce diffable files.
Each file is written to a temporary path and renamed into place, so a failed
export never leaves a partial CSV; a rerun overwrites.

Usage: .venv/bin/python -m ingest.export
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import require_postgres_dsn  # noqa: E402

EXPORT_DIR = REPO_ROOT / "exports"
SCHEMA = "analytics"

ROUND_DECIMALS = 6


class Mart:
    def __init__(self, columns: list[str], rounded: set[str], order_by: list[str]) -> None:
        unknown = rounded - set(columns)
        if unknown:
            raise ValueError(f"rounded columns not exported: {sorted(unknown)}")
        self.columns = columns
        self.rounded = rounded
        self.order_by = order_by


# Every exported column is listed, so a new mart column is never exported
# unrounded by accident. rounded: ratio and share columns only.
MARTS: dict[str, Mart] = {
    "fct_exposure_summary": Mart(
        columns=[
            "basket", "canonical_product_id", "hs6_code", "hs_version", "year",
            "weighting", "dest_coast",
            "flow_max_chokepoint", "flow_max_exposure_200", "flow_exposure_100", "flow_exposure_300",
            "risk_max_chokepoint", "risk_max_exposure_200", "risk_exposure_100", "risk_exposure_300",
            "gen_val_total", "cnt_val_total", "vessel_coverage", "unrouted_share", "coast_residual",
            "hhi", "effective_suppliers", "top1_partner_name", "top1_share",
        ],
        rounded={
            "flow_max_exposure_200", "flow_exposure_100", "flow_exposure_300",
            "risk_max_exposure_200", "risk_exposure_100", "risk_exposure_300",
            "vessel_coverage", "unrouted_share", "coast_residual",
            "hhi", "effective_suppliers", "top1_share",
        },
        order_by=["hs6_code", "year", "weighting", "dest_coast"],
    ),
    "fct_supplier_share": Mart(
        columns=[
            "basket", "canonical_product_id", "year", "partner_code", "partner_iso3",
            "partner_name", "is_aggregate_partner", "import_value_usd", "share", "rank",
        ],
        rounded={"share"},
        order_by=["canonical_product_id", "year", "rank"],
    ),
    "fct_concentration": Mart(
        columns=[
            "basket", "canonical_product_id", "year", "total_import_value_usd", "hhi",
            "effective_suppliers", "top1_partner_name", "top1_partner_iso3", "top1_share",
            "top3_share", "supplier_count", "n_codes",
        ],
        rounded={"hhi", "effective_suppliers", "top1_share", "top3_share"},
        order_by=["canonical_product_id", "year"],
    ),
    # Diagnostics (gen_val_total, cnt_val_total, vessel_coverage,
    # unrouted_share, coast_residual) omitted: see module docstring.
    "fct_exposure": Mart(
        columns=[
            "basket", "canonical_product_id", "hs6_code", "hs_version", "year",
            "chokepoint_id", "chokepoint_name", "threshold_km", "weighting", "dest_coast",
            "exposure",
        ],
        rounded={"exposure"},
        order_by=["hs6_code", "year", "chokepoint_id", "threshold_km", "weighting", "dest_coast"],
    ),
}


def _select_item(column: str, rounded: bool) -> sql.Composable:
    ident = sql.Identifier(column)
    if not rounded:
        return ident
    return sql.SQL("round({}, {}) AS {}").format(ident, sql.Literal(ROUND_DECIMALS), ident)


def export_table(cur: psycopg.Cursor, table: str, mart: Mart) -> int:
    query = sql.SQL("COPY (SELECT {} FROM {} ORDER BY {}) TO STDOUT WITH (FORMAT csv, HEADER true)").format(
        sql.SQL(", ").join(_select_item(c, c in mart.rounded) for c in mart.columns),
        sql.Identifier(SCHEMA, table),
        sql.SQL(", ").join(sql.Identifier(c) for c in mart.order_by),
    )
    path = EXPORT_DIR / f"{table}.csv"
    tmp = path.with_suffix(".csv.tmp")
    try:
        with tmp.open("wb") as f, cur.copy(query) as copy:
            for chunk in copy:
                f.write(chunk)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)

    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(SCHEMA, table)))
    return cur.fetchone()[0]


def main() -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    with psycopg.connect(require_postgres_dsn()) as conn, conn.cursor() as cur:
        for table, mart in MARTS.items():
            rows = export_table(cur, table, mart)
            size_mb = (EXPORT_DIR / f"{table}.csv").stat().st_size / 1e6
            print(f"exports/{table}.csv: {rows} rows, {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
