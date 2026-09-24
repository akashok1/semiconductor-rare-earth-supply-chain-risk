"""Census ingest: US imports by HS6 code from the Census international trade
API, two pulls per bridge code, plus the Schedule D port list and the
Schedule C country list.

  - imports/hs by partner country, with general, air, vessel and
    containerized-vessel value (GEN/AIR/VES/CNT_VAL_YR), cached to
    data/raw/census_hs_annual_{code}.json.
  - imports/porths by US port of entry, with general and vessel value
    (GEN/VES_VAL_YR), cached to data/raw/census_porths_vessel_{code}.json.
  - Schedule D district/port list (plain text, no key), cached to
    data/raw/census_schedule_d_ports.txt and parsed into
    data/reference/generated/census_ports.csv.
  - Schedule C country list (plain text, no key), cached to
    data/raw/census_schedule_c_countries.txt and joined to ISO 3166-1
    alpha-3 into data/reference/generated/census_country_crosswalk.csv.

Schedule D is one pipe-delimited table sorted by name, each row
"name | code | District" (2-digit code) or "name | code | Port" (4-digit).
It has no port-to-district column. district_code is the port code's first
two digits, the CBP convention; the April 2025 list gives a district row for
every such prefix except 46 (port 4671, FedEx ECCF Newark), which is written
with an empty district_name. A port listed in porths_vessel but missing from
Schedule D is reported, not dropped.

Schedule C is one pipe-delimited table, "code | name | ISO Code", the ISO
code being alpha-2 only. iso3 comes from pycountry (offline ISO 3166-1) by
alpha-2. A code it cannot match takes its iso3 from
data/reference/manual/country_crosswalk_overrides.csv, where a blank iso3
with a reason means no official code exists. Unmatched codes and Census
CTY_CODEs absent from Schedule C are reported.

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

The Schedule D file, fresh or cached, must parse: title and column header
present, every table row a District with a 2-digit code or a Port with a
4-digit code, no duplicate codes, at least one of each. Schedule C the
same: title and header present, every row a 4-digit code, a name and a
2-letter ISO code, no duplicate codes.

A cached file makes zero calls and is only read, never rewritten.
--refresh <code|all> re-pulls both sources for that code, validates, writes
to a temp file and only then moves it over the cached file, so a failed
refresh leaves the cache intact. --refresh schedule_d and --refresh
schedule_c do the same for the Schedule D and Schedule C lists; all
includes both.

Census accepts the API key only as a query param. No exception message, log
line or print includes the request URL or the key: requests exceptions are
re-raised without their URL-bearing message, and response bodies are quoted
only with the key redacted.

Usage: .venv/bin/python -m ingest.census [--refresh {CODE,schedule_d,schedule_c,all}]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pycountry
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import (  # noqa: E402
    CENSUS_IMPORTS_HS_URL,
    CENSUS_IMPORTS_PORTHS_URL,
    CENSUS_SCHEDULE_C_COUNTRIES_URL,
    CENSUS_SCHEDULE_D_PORTS_URL,
    YEAR_END,
    YEAR_START,
    require_census_api_key,
)
from ingest.hs_bridge import OUTPUT_PATH as HS_BRIDGE_PATH  # noqa: E402
from ingest.hs_bridge import read_vintage_plan  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"
SCHEDULE_D_CACHE = CACHE_DIR / "census_schedule_d_ports.txt"
SCHEDULE_C_CACHE = CACHE_DIR / "census_schedule_c_countries.txt"
CENSUS_PORTS_PATH = REPO_ROOT / "data" / "reference" / "generated" / "census_ports.csv"
CROSSWALK_PATH = REPO_ROOT / "data" / "reference" / "generated" / "census_country_crosswalk.csv"
COUNTRY_OVERRIDES_PATH = REPO_ROOT / "data" / "reference" / "manual" / "country_crosswalk_overrides.csv"

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


SCHEDULE_D_TITLE = "Schedule D - District/Port List"
SCHEDULE_D_COLUMNS = ("Name", "Code", "District/Port")


def parse_schedule_d(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse the Schedule D list into ({district_code: name},
    {port_code: name}). Raises CensusValidationError unless the file has its
    title and column header, every table row is a District with a 2-digit
    code or a Port with a 4-digit code, no code repeats, and both kinds
    appear."""
    label = SCHEDULE_D_CACHE.name
    lines = text.splitlines()
    if not any(line.startswith(SCHEDULE_D_TITLE) for line in lines):
        raise CensusValidationError(f"{label}: title {SCHEDULE_D_TITLE!r} not found.")

    districts: dict[str, str] = {}
    ports: dict[str, str] = {}
    seen_header = False
    for n, line in enumerate(lines, start=1):
        if "|" not in line:
            continue
        cells = tuple(c.strip() for c in line.split("|"))
        if cells == SCHEDULE_D_COLUMNS:
            seen_header = True
            continue
        if len(cells) != 3:
            raise CensusValidationError(f"{label}: line {n} has {len(cells)} cells: {line!r}.")
        name, code, kind = cells
        target, width = {"District": (districts, 2), "Port": (ports, 4)}.get(kind, (None, 0))
        if target is None or not (code.isdigit() and len(code) == width) or not name:
            raise CensusValidationError(f"{label}: line {n} unrecognised: {line!r}.")
        if code in target:
            raise CensusValidationError(f"{label}: {kind} code {code} appears twice.")
        target[code] = name

    if not seen_header:
        raise CensusValidationError(f"{label}: column header {SCHEDULE_D_COLUMNS} not found.")
    if not districts or not ports:
        raise CensusValidationError(
            f"{label}: {len(districts)} district and {len(ports)} port rows; need both."
        )
    return districts, ports


def _pull_text(cache_file: Path, url: str, parse, force: bool) -> tuple[object, int]:
    """Return (parse(text), API calls made) for a plain-text Census schedule.
    A cached file is parsed, never rewritten, unless force. A fresh body is
    written only once it parses, via a temp file."""
    if cache_file.exists() and not force:
        return parse(cache_file.read_text()), 0

    label = cache_file.name
    try:
        resp = requests.get(url, timeout=120)
    except requests.RequestException as exc:
        raise CensusFetchError(f"{label}: request failed ({type(exc).__name__}). Nothing written.") from None
    if resp.status_code != 200:
        raise CensusFetchError(f"{label}: HTTP {resp.status_code}: {resp.text[:500]}. Nothing written.")
    if not resp.content.strip():
        raise CensusFetchError(f"{label}: HTTP 200 with empty body. Nothing written.")
    parsed = parse(resp.text)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CACHE_DIR / f".tmp_{label}"
    try:
        temp_file.write_bytes(resp.content)
        temp_file.replace(cache_file)
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise
    return parsed, 1


def pull_schedule_d(force: bool) -> tuple[dict[str, str], dict[str, str], int]:
    """Return (districts, ports, API calls made)."""
    (districts, ports), calls = _pull_text(
        SCHEDULE_D_CACHE, CENSUS_SCHEDULE_D_PORTS_URL, parse_schedule_d, force
    )
    return districts, ports, calls


SCHEDULE_C_TITLE = "Schedule C - Country List"
SCHEDULE_C_COLUMNS = ("Code", "Name", "ISO Code")


def parse_schedule_c(text: str) -> dict[str, tuple[str, str]]:
    """Parse the Schedule C list into {cty_code: (cty_name, iso2)}. Raises
    CensusValidationError unless the file has its title and column header,
    every table row is a 4-digit code, a name and a 2-letter uppercase ISO
    code, no code repeats, and at least one row appears."""
    label = SCHEDULE_C_CACHE.name
    lines = text.splitlines()
    if not any(line.startswith(SCHEDULE_C_TITLE) for line in lines):
        raise CensusValidationError(f"{label}: title {SCHEDULE_C_TITLE!r} not found.")

    countries: dict[str, tuple[str, str]] = {}
    seen_header = False
    for n, line in enumerate(lines, start=1):
        if "|" not in line:
            continue
        cells = tuple(c.strip() for c in line.split("|"))
        if cells == SCHEDULE_C_COLUMNS:
            seen_header = True
            continue
        if len(cells) != 3:
            raise CensusValidationError(f"{label}: line {n} has {len(cells)} cells: {line!r}.")
        code, name, iso2 = cells
        if not (code.isdigit() and len(code) == 4 and name
                and len(iso2) == 2 and iso2.isalpha() and iso2.isupper()):
            raise CensusValidationError(f"{label}: line {n} unrecognised: {line!r}.")
        if code in countries:
            raise CensusValidationError(f"{label}: country code {code} appears twice.")
        countries[code] = (name, iso2)

    if not seen_header:
        raise CensusValidationError(f"{label}: column header {SCHEDULE_C_COLUMNS} not found.")
    if not countries:
        raise CensusValidationError(f"{label}: no country rows.")
    return countries


def pull_schedule_c(force: bool) -> tuple[dict[str, tuple[str, str]], int]:
    """Return ({cty_code: (cty_name, iso2)}, API calls made)."""
    return _pull_text(SCHEDULE_C_CACHE, CENSUS_SCHEDULE_C_COUNTRIES_URL, parse_schedule_c, force)


def _write_csv(path: Path, header: tuple[str, ...], rows: list[tuple]) -> None:
    """Write a generated CSV with LF line endings, via a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_name(f".tmp_{path.name}")
    try:
        with temp_file.open("w", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        temp_file.replace(path)
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise


def write_census_ports(districts: dict[str, str], ports: dict[str, str]) -> list[str]:
    """Write census_ports.csv (port_code, port_name, district_code,
    district_name), one row per Schedule D port, sorted by port_code.
    district_code is the port code's first two digits (see module
    docstring). Returns the port codes whose district has no Schedule D
    row; they are written with an empty district_name."""
    orphans = []
    rows = []
    for code in sorted(ports):
        district = code[:2]
        if district not in districts:
            orphans.append(code)
        rows.append((code, ports[code], district, districts.get(district, "")))
    _write_csv(CENSUS_PORTS_PATH, ("port_code", "port_name", "district_code", "district_name"), rows)
    return orphans


def read_country_overrides() -> dict[str, dict[str, str]]:
    """Read the manual crosswalk overrides, {cty_code: row}. Raises
    CensusValidationError on a wrong header, a repeated cty_code, an empty
    reason, or an iso3 that is neither blank nor three uppercase letters."""
    label = COUNTRY_OVERRIDES_PATH.name
    with COUNTRY_OVERRIDES_PATH.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["cty_code", "iso3", "reason"]:
            raise CensusValidationError(f"{label}: header {reader.fieldnames}, expected cty_code,iso3,reason.")
        overrides: dict[str, dict[str, str]] = {}
        for row in reader:
            code, iso3 = row["cty_code"], row["iso3"]
            if code in overrides:
                raise CensusValidationError(f"{label}: cty_code {code} appears twice.")
            if not row["reason"].strip():
                raise CensusValidationError(f"{label}: cty_code {code} has no reason.")
            if iso3 and not (len(iso3) == 3 and iso3.isalpha() and iso3.isupper()):
                raise CensusValidationError(f"{label}: cty_code {code} iso3 {iso3!r} is not blank or 3 letters.")
            overrides[code] = row
    return overrides


def write_country_crosswalk(countries: dict[str, tuple[str, str]]) -> list[str]:
    """Write census_country_crosswalk.csv (cty_code, cty_name, iso2, iso3,
    basis), one row per Schedule C country, sorted by cty_code. iso3 comes
    from pycountry by alpha-2 (basis iso3166); a code pycountry cannot match
    takes its iso3 from the manual overrides (basis manual_override, iso3
    possibly blank), else is written blank (basis unmatched). Raises if an
    override names a code pycountry already matches or a code Schedule C
    lacks. Returns the unmatched cty_codes."""
    overrides = read_country_overrides()
    stray = sorted(set(overrides) - set(countries))
    if stray:
        raise CensusValidationError(f"{COUNTRY_OVERRIDES_PATH.name}: codes {stray} are not in Schedule C.")

    rows = []
    unmatched = []
    for code in sorted(countries):
        name, iso2 = countries[code]
        match = pycountry.countries.get(alpha_2=iso2)
        if match and code in overrides:
            raise CensusValidationError(
                f"{COUNTRY_OVERRIDES_PATH.name}: {code} ({iso2}) already matches "
                f"ISO 3166 {match.alpha_3}; remove the override."
            )
        if match:
            rows.append((code, name, iso2, match.alpha_3, "iso3166"))
        elif code in overrides:
            rows.append((code, name, iso2, overrides[code]["iso3"], "manual_override"))
        else:
            rows.append((code, name, iso2, "", "unmatched"))
            unmatched.append(code)
    _write_csv(CROSSWALK_PATH, ("cty_code", "cty_name", "iso2", "iso3", "basis"), rows)
    return unmatched


def census_country_codes(codes: list[str]) -> dict[str, str]:
    """Every distinct country CTY_CODE (SUMMARY_LVL 'DET', excluding the '-'
    total) in the cached imports/hs files, with its CTY_NAME."""
    pull = PULLS["hs"]
    seen: dict[str, str] = {}
    for code in codes:
        header, *rows = json.loads(pull.cache_file(code).read_text())
        cty_idx, name_idx = header.index("CTY_CODE"), header.index("CTY_NAME")
        lvl_idx = header.index("SUMMARY_LVL")
        for row in rows:
            if row[lvl_idx] == "DET" and row[cty_idx] != "-":
                seen.setdefault(row[cty_idx], row[name_idx])
    return dict(sorted(seen.items()))


def porths_ports_missing_from_schedule_d(codes: list[str], ports: dict[str, str]) -> dict[str, str | None]:
    """Every distinct PORT (excluding the '-' total) in the cached
    porths_vessel files that Schedule D does not list, with the PORT_NAME
    Census returned for it."""
    pull = PULLS["porths_vessel"]
    seen: dict[str, str | None] = {}
    for code in codes:
        header, *rows = json.loads(pull.cache_file(code).read_text())
        port_idx, name_idx = header.index("PORT"), header.index("PORT_NAME")
        for row in rows:
            if row[port_idx] != "-":
                seen.setdefault(row[port_idx], row[name_idx])
    return {p: n for p, n in sorted(seen.items()) if p not in ports}


def main() -> None:
    required = load_required_years()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        choices=list(required) + ["schedule_d", "schedule_c", "all"],
        help="Re-pull both sources for this code (or all codes), or the "
        "Schedule D or Schedule C list, and replace each cached file only "
        "once the response validates.",
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

    print(f"  schedule_d -> {SCHEDULE_D_CACHE.name}")
    districts, ports, calls = pull_schedule_d(args.refresh in ("schedule_d", "all"))
    total_calls += calls
    orphans = write_census_ports(districts, ports)
    print(f"  schedule_d: {len(districts)} districts, {len(ports)} ports, {calls} API call(s)")
    print(f"    wrote {CENSUS_PORTS_PATH.relative_to(REPO_ROOT)}")
    for code in orphans:
        print(f"    port {code} {ports[code]}: no district row for {code[:2]}, district_name empty")
    missing = porths_ports_missing_from_schedule_d(list(required), ports)
    print(f"    porths_vessel ports not in Schedule D: {len(missing)}")
    for code, name in missing.items():
        print(f"      {code} {name}")

    print(f"  schedule_c -> {SCHEDULE_C_CACHE.name}")
    countries, calls = pull_schedule_c(args.refresh in ("schedule_c", "all"))
    total_calls += calls
    unmatched = write_country_crosswalk(countries)
    print(f"  schedule_c: {len(countries)} countries, {calls} API call(s)")
    print(f"    wrote {CROSSWALK_PATH.relative_to(REPO_ROOT)}")
    in_data = census_country_codes(list(required))
    for code in unmatched:
        where = "in Census data, needs an override" if code in in_data else "not in Census data"
        print(f"    unmatched {code} {countries[code][0]} ({countries[code][1]}): {where}")
    not_listed = {c: n for c, n in in_data.items() if c not in countries}
    print(f"    Census CTY_CODEs not in Schedule C: {len(not_listed)}")
    for code, name in not_listed.items():
        print(f"      {code} {name}")
    print(f"Done. {total_calls} API call(s) total.")


if __name__ == "__main__":
    main()
