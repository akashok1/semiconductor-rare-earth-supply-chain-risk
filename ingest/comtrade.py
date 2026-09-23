"""Comtrade ingest: US annual imports, 2022-2025, HS2022 (H6), all basket codes.

Four calls, one per year, each covering every H6 code in
data/reference/hs_bridge.csv at once (comma-joined cmdCode, per
docs/07_assumptions_limitations.md and CLAUDE.md this is a single call per
year, not per code). 2018-2021 (H5) is already cached from
analysis/verification_round1.py; this script only extends the range forward
across the 2021/2022 classification break, per hs_bridge.csv.

Queries go to /get/C/A/HS (combined classification), not /get/C/A/H6: the
latter returns HTTP 500 for every request, empirically (a specific-vintage
clCode is accepted by Comtrade's availability/reference endpoints but not by
this data endpoint). /get/C/A/HS returns each reporter's native
classification per period -- H6 for 2022 onward -- and every row's actual
vintage still comes back in classificationCode, same as the already-cached
2018-2021 (H5) files pulled the same way by
analysis/verification_round1.py.

The ``comtradeapicall`` package (CLAUDE.md's stated architecture for this
source) is not used here: its ``getFinalData`` swallows non-200 responses by
printing the body and returning ``None`` rather than raising, which cannot
satisfy "fail loudly on 401 or any auth failure" below. This script instead
follows the raw-``requests`` pattern already proven in
analysis/verification_round1.py and ingest/reference.py, and produces
byte-identical cache-file shape to the existing 2018-2021 files. See the
FINDINGS block accompanying the commit that introduced this file.

Usage: .venv/bin/python -m ingest.comtrade
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import COMTRADE_DATA_BASE, require_comtrade_api_key  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"
HS_BRIDGE_PATH = REPO_ROOT / "data" / "reference" / "hs_bridge.csv"

REPORTER_USA = "842"
FLOW_IMPORT = "M"
CUSTOMS_ALL = "C00"

HS_VERSION = "H6"
YEARS = [2022, 2023, 2024, 2025]


class ComtradeAuthError(RuntimeError):
    """Raised on HTTP 401/403 from the Comtrade API. Never includes the key."""


class ComtradeCodeCountError(RuntimeError):
    """Raised when a year's response covers a different set of codes than
    hs_bridge.csv says it should."""


def _comtrade_headers() -> dict:
    # Subscription key travels as a header, never as a query param, so it
    # can never end up in a cached URL, a raised exception's message, or a
    # log line.
    return {"Ocp-Apim-Subscription-Key": require_comtrade_api_key()}


def _load_h6_codes() -> list[str]:
    """Distinct HS6 codes for hs_version == H6, from hs_bridge.csv. Not from
    data/reference/basket_selection.csv -- that file predates the bridge and
    does not reflect the 2022 classification split."""
    codes: set[str] = set()
    with HS_BRIDGE_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["hs_version"] == HS_VERSION:
                codes.add(row["hs6_code"])
    return sorted(codes)


def _fetch_year(cache_name: str, year: int, codes: list[str]) -> dict:
    """GET one year of final trade data for every code at once, caching the
    raw JSON response under data/raw/cache_name. Raises ComtradeAuthError on
    401/403 before writing anything to disk. Retries once on 429."""
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    params = {
        "reporterCode": REPORTER_USA,
        "period": year,
        "cmdCode": ",".join(codes),
        "flowCode": FLOW_IMPORT,
        "partner2Code": 0,
        "customsCode": CUSTOMS_ALL,
        "motCode": 0,
    }

    resp = None
    for attempt in range(3):
        resp = requests.get(
            f"{COMTRADE_DATA_BASE}/get/C/A/HS",
            params=params,
            headers=_comtrade_headers(),
            timeout=120,
        )
        if resp.status_code in (401, 403):
            raise ComtradeAuthError(
                f"Comtrade final trade data for {year} failed with HTTP "
                f"{resp.status_code}. COMTRADE_API_KEY may be missing, "
                "invalid, expired, or regenerated. Nothing was written to "
                "disk for this call."
            )
        if resp.status_code == 429 and attempt < 2:
            time.sleep(3 * (attempt + 1))
            continue
        break
    resp.raise_for_status()

    payload = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, indent=2))
    time.sleep(1.5)  # stay well under the free-tier rate limit
    return payload


def _validate_code_coverage(year: int, payload: dict, expected_codes: list[str]) -> None:
    seen_codes = {row["cmdCode"] for row in payload.get("data", [])}
    expected_count = len(expected_codes)
    seen_count = len(seen_codes)
    if seen_count != expected_count:
        raise ComtradeCodeCountError(
            f"{year}: response covers {seen_count} distinct cmdCode value(s), "
            f"expected {expected_count} from data/reference/hs_bridge.csv "
            f"(hs_version={HS_VERSION}). Seen: {sorted(seen_codes)}. "
            f"Expected: {expected_codes}."
        )


def pull_year(year: int, codes: list[str]) -> Path:
    cache_name = f"comtrade_final_C_A_HS_{year}.json"
    cache_file = CACHE_DIR / cache_name
    already_cached = cache_file.exists()

    payload = _fetch_year(cache_name, year, codes)
    _validate_code_coverage(year, payload, codes)

    if already_cached:
        print(f"  {year}: already cached ({cache_name}), 0 API calls")
    else:
        print(f"  {year}: fetched and cached ({cache_name})")
    return cache_file


def main() -> None:
    print(f"Loading {HS_VERSION} code list from {HS_BRIDGE_PATH.relative_to(REPO_ROOT)}...")
    codes = _load_h6_codes()
    print(f"  {len(codes)} code(s): {codes}")

    print(f"Pulling Comtrade final trade data for {YEARS}...")
    for year in YEARS:
        pull_year(year, codes)

    print("Done.")


if __name__ == "__main__":
    main()
