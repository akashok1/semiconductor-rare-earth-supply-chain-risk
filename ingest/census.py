"""Census ingest: US imports by HS6 code from the Census international trade
API, two pulls per bridge code.

  - imports/hs by partner country, with general, air, vessel and
    containerized-vessel value (GEN/AIR/VES/CNT_VAL_YR), cached to
    data/raw/census_hs_annual_{code}.json.
  - imports/porths by US port of entry, with general and vessel value
    (GEN/VES_VAL_YR), cached to data/raw/census_porths_vessel_{code}.json.

Codes are every distinct hs6_code in data/reference/generated/hs_bridge.csv.
Comma-joined I_COMMODITY returns HTTP 204, so each code is one call per pull,
covering the full monthly range "from {YEAR_START}-01 to {YEAR_END}-12"
(years from config).

Operational facts for anyone reading the raw files:
  - Rows are monthly. The _YR fields are YEAR-TO-DATE CUMULATIVE, so the
    December row is the calendar-year total. Summing across months inflates
    values roughly 6.2x.
  - Rows mix country/port detail (SUMMARY_LVL 'DET') with regional
    aggregates ('CGP'), and the grand total row (CTY_CODE or PORT '-') is
    also tagged 'DET'. Keeping December, SUMMARY_LVL = 'DET' and dropping
    the '-' sentinel happens in dbt staging, not here. Raw files keep every
    row the API returned.
  - Census echoes the predicate params back as trailing columns, so each
    header is the requested field list followed by COMM_LVL, I_COMMODITY and
    time (I_COMMODITY appears twice). expected_header() returns it;
    load.py reads it from here.

Every response, fresh or cached, is validated before use:
  - HTTP 204 or an empty body (no header, or a header with no rows) raises,
  - the header equals expected_header() exactly,
  - every row's I_COMMODITY (both columns) equals the requested code,
  - every time value falls inside {YEAR_START}-01..{YEAR_END}-12,
  - every year the bridge says the code must cover has a December row. A
    code with an H5 row must cover years before vintage_break_year; a code
    with an H6 row must cover vintage_break_year onward.
A fresh response that fails is never written. A cached file that fails
raises, so a bad cache fails loudly.

A cached file makes zero calls and is only read, never rewritten.
--refresh <code|all> re-pulls both sources for that code, validates, writes
to a temp file and only then moves it over the cached file, so a failed
refresh leaves the cache intact.

Census accepts the API key only as a query param. No exception message, log
line or print includes the request URL or the key: requests exceptions are
re-raised without their URL-bearing message, and response bodies are quoted
only with the key redacted.

Usage: .venv/bin/python -m ingest.census [--refresh {CODE,all}]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import (  # noqa: E402
    CENSUS_IMPORTS_HS_URL,
    CENSUS_IMPORTS_PORTHS_URL,
    YEAR_END,
    YEAR_START,
    require_census_api_key,
)
from ingest.hs_bridge import OUTPUT_PATH as HS_BRIDGE_PATH  # noqa: E402
from ingest.hs_bridge import read_vintage_plan  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"

COMM_LVL = "HS6"
TIME_RANGE = f"from {YEAR_START}-01 to {YEAR_END}-12"
TIME_MIN = f"{YEAR_START}-01"
TIME_MAX = f"{YEAR_END}-12"

# Requested fields, in request order.
HS_FIELDS = (
    "I_COMMODITY", "CTY_CODE", "CTY_NAME", "SUMMARY_LVL",
    "GEN_VAL_YR", "AIR_VAL_YR", "VES_VAL_YR", "CNT_VAL_YR",
)
PORTHS_VESSEL_FIELDS = (
    "I_COMMODITY", "PORT", "PORT_NAME", "SUMMARY_LVL",
    "GEN_VAL_YR", "VES_VAL_YR",
)
# Predicate params Census echoes back as trailing columns, in param order.
ECHOED_PREDICATES = ("COMM_LVL", "I_COMMODITY", "time")


@dataclass(frozen=True)
class Pull:
    name: str
    url: str
    fields: tuple[str, ...]
    cache_prefix: str

    def cache_file(self, code: str) -> Path:
        return CACHE_DIR / f"{self.cache_prefix}_{code}.json"


PULLS = {
    "hs": Pull("hs", CENSUS_IMPORTS_HS_URL, HS_FIELDS, "census_hs_annual"),
    "porths_vessel": Pull(
        "porths_vessel", CENSUS_IMPORTS_PORTHS_URL, PORTHS_VESSEL_FIELDS,
        "census_porths_vessel",
    ),
}


class CensusAuthError(RuntimeError):
    """Raised on HTTP 401/403. Never includes the URL or the key."""


class CensusFetchError(RuntimeError):
    """Raised on HTTP 204, any other non-200, or a transport failure. Never
    includes the URL or the key."""


class CensusValidationError(RuntimeError):
    """Raised when a response (fresh or cached) fails validation."""


def expected_header(pull: str) -> list[str]:
    """The exact header row Census returns for a pull ('hs' or
    'porths_vessel'): requested fields, then the echoed predicates."""
    return list(PULLS[pull].fields) + list(ECHOED_PREDICATES)


def load_required_years() -> dict[str, list[int]]:
    """Map each distinct bridge hs6_code to the years it must cover, from the
    vintage split in hs_bridge.csv (read_vintage_plan, which raises
    HsBridgeVintageError if the split is ambiguous). Years before the break
    if the code has a row at the older hs_version, years from it onward if it
    has a row at the newer one."""
    vintage = read_vintage_plan()
    old_years = range(YEAR_START, vintage.break_year)
    new_years = range(vintage.break_year, YEAR_END + 1)

    required: dict[str, set[int]] = {}
    for code in vintage.codes_by_version[vintage.old_version]:
        required.setdefault(code, set()).update(old_years)
    for code in vintage.codes_by_version[vintage.new_version]:
        required.setdefault(code, set()).update(new_years)
    return {code: sorted(years) for code, years in sorted(required.items())}


def validate(pull: Pull, code: str, payload, required_years: list[int]) -> dict:
    """Raise CensusValidationError unless the payload passes every check in
    the module docstring. Returns a summary: row count and the December
    presence of each required year."""
    label = f"{pull.cache_prefix}_{code}"
    if not isinstance(payload, list) or not payload:
        raise CensusValidationError(f"{label}: empty body.")

    header, *rows = payload
    expected = expected_header(pull.name)
    if header != expected:
        raise CensusValidationError(
            f"{label}: header {header} does not equal expected {expected}."
        )
    if not rows:
        raise CensusValidationError(f"{label}: header only, no data rows.")

    commodity_idx = [i for i, h in enumerate(header) if h == "I_COMMODITY"]
    time_idx = header.index("time")
    december_years: set[int] = set()
    for n, row in enumerate(rows, start=1):
        if len(row) != len(header):
            raise CensusValidationError(
                f"{label}: row {n} has {len(row)} values, header has {len(header)}."
            )
        commodities = {row[i] for i in commodity_idx}
        if commodities != {code}:
            raise CensusValidationError(
                f"{label}: row {n} I_COMMODITY {sorted(commodities)}, expected {code}."
            )
        t = row[time_idx]
        if not (isinstance(t, str) and len(t) == 7 and t[4] == "-"
                and TIME_MIN <= t <= TIME_MAX):
            raise CensusValidationError(
                f"{label}: row {n} time {t!r} outside {TIME_MIN}..{TIME_MAX}."
            )
        if t.endswith("-12"):
            december_years.add(int(t[:4]))

    missing = [y for y in required_years if y not in december_years]
    if missing:
        raise CensusValidationError(
            f"{label}: no December row for required year(s) {missing} "
            f"(required by hs_bridge.csv: {required_years})."
        )
    return {"rows": len(rows), "december": {y: y in december_years for y in required_years}}


def _fetch(pull: Pull, code: str) -> list:
    """GET one code over the full time range. Raises CensusAuthError on
    401/403 and CensusFetchError on 204, any other non-200, a transport
    failure or a non-JSON body. Writes nothing."""
    label = f"{pull.cache_prefix}_{code}"
    api_key = require_census_api_key()
    params = {
        "get": ",".join(pull.fields),
        "COMM_LVL": COMM_LVL,
        "I_COMMODITY": code,
        "time": TIME_RANGE,
        "key": api_key,
    }
    try:
        resp = requests.get(pull.url, params=params, timeout=120)
    except requests.RequestException as exc:
        # requests' messages carry the full URL, key included. Drop them.
        raise CensusFetchError(
            f"{label}: request failed ({type(exc).__name__}). Nothing written."
        ) from None

    if resp.status_code in (401, 403):
        raise CensusAuthError(
            f"{label}: HTTP {resp.status_code}. CENSUS_API_KEY may be missing, "
            "invalid or expired. Nothing written."
        )
    if resp.status_code == 204:
        raise CensusFetchError(f"{label}: HTTP 204, no content. Nothing written.")
    if resp.status_code != 200:
        body = resp.text[:500].replace(api_key, "***REDACTED***")
        raise CensusFetchError(
            f"{label}: HTTP {resp.status_code}: {body}. Nothing written."
        )
    if not resp.content.strip():
        raise CensusFetchError(f"{label}: HTTP 200 with empty body. Nothing written.")
    try:
        return resp.json()
    except ValueError:
        raise CensusFetchError(f"{label}: HTTP 200 body is not JSON. Nothing written.") from None


def pull_code(pull: Pull, code: str, required_years: list[int], force: bool) -> tuple[dict, int]:
    """Return (validation summary, API calls made) for one code of one pull.
    A cached file is read and validated, never rewritten, unless force."""
    cache_file = pull.cache_file(code)
    if cache_file.exists() and not force:
        payload = json.loads(cache_file.read_text())
        return validate(pull, code, payload, required_years), 0

    payload = _fetch(pull, code)
    summary = validate(pull, code, payload, required_years)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CACHE_DIR / f".tmp_{cache_file.name}"
    try:
        temp_file.write_text(json.dumps(payload))
        temp_file.replace(cache_file)
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise
    time.sleep(0.5)
    return summary, 1


def main() -> None:
    required = load_required_years()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        choices=list(required) + ["all"],
        help="Re-pull both sources for this code (or all codes) and replace "
        "each cached file only once the response validates.",
    )
    args = parser.parse_args()

    print(f"Census imports, {TIME_RANGE}, {len(required)} codes from "
          f"{HS_BRIDGE_PATH.relative_to(REPO_ROOT)}")
    total_calls = 0
    for pull in PULLS.values():
        files = calls = 0
        print(f"  {pull.name} -> {pull.cache_prefix}_{{code}}.json")
        for code, years in required.items():
            force = args.refresh in (code, "all")
            summary, n = pull_code(pull, code, years, force)
            files += 1
            calls += n
            dec = " ".join(f"{y}:{'Y' if ok else 'N'}" for y, ok in summary["december"].items())
            print(f"    {code}: {summary['rows']:>6} rows, December {dec}, {n} call(s)")
        print(f"  {pull.name}: {files} files validated, {calls} API call(s)")
        total_calls += calls
    print(f"Done. {total_calls} API call(s) total.")


if __name__ == "__main__":
    main()
