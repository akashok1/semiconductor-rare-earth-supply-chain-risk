"""Comtrade ingest: US annual imports by partner, every bridge code, every
project year.

Years come from config (YEAR_START..YEAR_END). The HS vintage requested for
each year comes from data/reference/generated/hs_bridge.csv: the bridge's
single non-null vintage_break_year splits the range, years before it use the
older hs_version's code list and years from it onward the newer one's. Each
code list is the distinct hs6_code values for that hs_version. One call per
year covers every code at once (comma-joined cmdCode).

Queries go to /get/C/A/HS, not /get/C/A/H5 or /H6: the vintage-specific
endpoints return HTTP 500. /get/C/A/HS returns the reporter's native vintage
per period, and each row reports it in classificationCode.

Every response, fresh or cached, is validated before use:
  - the distinct cmdCode set equals the bridge code list exactly,
  - every row's classificationCode equals the expected hs_version,
  - the "error" field is empty.
A fresh response that fails is never written to disk. A cached file that
fails raises, so a bad cache fails loudly.

Each year caches to data/raw/comtrade_final_C_A_HS_{year}.json. A cached year
makes zero calls and its file is only read. --refresh <year|all> ignores the
cache for that year, fetches, validates, writes to a temp file and only then
moves it over the cached file, so a failed refresh leaves the cache intact.

The API key travels only as a request header. HTTP 401/403 raises
ComtradeAuthError before anything is written; 429 is retried with backoff;
any other non-200 raises. comtradeapicall is not used because it swallows
non-200 responses and returns None.

Usage: .venv/bin/python -m ingest.comtrade [--refresh {YEAR,all}]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import (  # noqa: E402
    COMTRADE_DATA_BASE,
    YEAR_END,
    YEAR_START,
    require_comtrade_api_key,
)

CACHE_DIR = REPO_ROOT / "data" / "raw"
HS_BRIDGE_PATH = REPO_ROOT / "data" / "reference" / "generated" / "hs_bridge.csv"

REPORTER_USA = "842"
FLOW_IMPORT = "M"
CUSTOMS_ALL = "C00"

YEARS = range(YEAR_START, YEAR_END + 1)


class ComtradeAuthError(RuntimeError):
    """Raised on HTTP 401/403 from the Comtrade API. Never includes the key."""


class ComtradeBridgeError(RuntimeError):
    """Raised when hs_bridge.csv does not define an unambiguous vintage split."""


class ComtradeValidationError(RuntimeError):
    """Raised when a response (fresh or cached) does not match what
    hs_bridge.csv says the year should contain."""


def _comtrade_headers() -> dict:
    # Subscription key travels as a header, never as a query param, so it
    # can never end up in a cached URL, a raised exception's message, or a
    # log line.
    return {"Ocp-Apim-Subscription-Key": require_comtrade_api_key()}


def _cache_file(year: int) -> Path:
    return CACHE_DIR / f"comtrade_final_C_A_HS_{year}.json"


def load_year_plan() -> dict[int, tuple[str, list[str]]]:
    """Map each project year to (hs_version, sorted code list), from
    hs_bridge.csv. Raises unless the bridge has exactly one distinct non-null
    vintage_break_year and exactly two hs_versions."""
    with HS_BRIDGE_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))

    breaks = {r["vintage_break_year"] for r in rows if r["vintage_break_year"].strip()}
    if len(breaks) != 1:
        raise ComtradeBridgeError(
            f"hs_bridge.csv has {len(breaks)} distinct non-null "
            f"vintage_break_year value(s) {sorted(breaks)}, expected exactly one."
        )
    break_year = int(breaks.pop())

    codes_by_version: dict[str, set[str]] = {}
    for r in rows:
        codes_by_version.setdefault(r["hs_version"], set()).add(r["hs6_code"])
    if len(codes_by_version) != 2:
        raise ComtradeBridgeError(
            f"hs_bridge.csv has hs_version values {sorted(codes_by_version)}, "
            "expected exactly two (one each side of the vintage break)."
        )
    old_version, new_version = sorted(codes_by_version)

    plan = {}
    for year in YEARS:
        version = old_version if year < break_year else new_version
        plan[year] = (version, sorted(codes_by_version[version]))
    return plan


def validate(year: int, payload: dict, hs_version: str, codes: list[str]) -> set[str]:
    """Raise ComtradeValidationError unless the payload's code set,
    classificationCode and error field are what the bridge expects. Returns
    the set of classificationCode values seen."""
    error = payload.get("error")
    if error:
        raise ComtradeValidationError(f"{year}: response carries error: {error!r}")

    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ComtradeValidationError(f"{year}: response has no data list.")

    seen = {r["cmdCode"] for r in rows}
    expected = set(codes)
    if seen != expected:
        raise ComtradeValidationError(
            f"{year}: cmdCode set does not match hs_bridge.csv "
            f"(hs_version={hs_version}). Missing: {sorted(expected - seen)}. "
            f"Unexpected: {sorted(seen - expected)}."
        )

    classifications = {r["classificationCode"] for r in rows}
    if classifications != {hs_version}:
        raise ComtradeValidationError(
            f"{year}: classificationCode values {sorted(classifications)}, "
            f"expected only {hs_version}."
        )
    return classifications


def _fetch(year: int, codes: list[str]) -> dict:
    """GET one year for every code at once. Raises ComtradeAuthError on
    401/403, retries on 429, raises on any other non-200. Writes nothing."""
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
    return resp.json()


def pull_year(year: int, hs_version: str, codes: list[str], force: bool) -> tuple[set[str], int]:
    """Return (classificationCode values seen, API calls made) for one year.
    A cached year is read and validated, never rewritten, unless force."""
    cache_file = _cache_file(year)
    if cache_file.exists() and not force:
        payload = json.loads(cache_file.read_text())
        return validate(year, payload, hs_version, codes), 0

    payload = _fetch(year, codes)
    classifications = validate(year, payload, hs_version, codes)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CACHE_DIR / f".tmp_{cache_file.name}"
    try:
        temp_file.write_text(json.dumps(payload, indent=2))
        temp_file.replace(cache_file)
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise
    time.sleep(1.5)  # stay well under the free-tier rate limit
    return classifications, 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        choices=[str(y) for y in YEARS] + ["all"],
        help="Ignore the cache for this year (or all years), fetch fresh, and "
        "replace the cached file only once the response validates.",
    )
    args = parser.parse_args()

    plan = load_year_plan()
    total_calls = 0
    print(f"Comtrade final trade data, {YEAR_START}-{YEAR_END}, codes from "
          f"{HS_BRIDGE_PATH.relative_to(REPO_ROOT)}")
    for year, (hs_version, codes) in plan.items():
        force = args.refresh in (str(year), "all")
        classifications, calls = pull_year(year, hs_version, codes, force)
        total_calls += calls
        print(
            f"  {year}: expected {hs_version}, {len(codes)} codes, "
            f"classificationCode {sorted(classifications)}, {calls} API call(s)"
        )
    print(f"Done. {total_calls} API call(s) total.")


if __name__ == "__main__":
    main()
