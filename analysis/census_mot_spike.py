"""Census mode-of-transport and port-of-entry spike (verification round 2, task 3).

Comtrade doesn't report a mode-of-transport breakdown for the US (see
verification_round2.md task 2). This spike checks whether the Census Bureau's
own international trade API can supply that instead: air vs. vessel vs. other
mode, and which US ports of entry the 22 candidate HS6 codes clear through.

Two Census timeseries endpoints:
  - imports/hs: value by commodity and partner country, with GEN/AIR/VES/CNT
    value fields (general, air, vessel, containerized-vessel).
  - imports/porths: value by commodity and US port of entry. Also carries
    CTY_CODE/CTY_NAME (confirmed via the endpoint's own variables.json before
    writing this script).

Both endpoints are monthly (_MO fields) but also expose year-to-date (_YR)
fields. Querying December of each year with the _YR fields gives the full
calendar-year total in one row per code/country/port, instead of pulling and
summing 12 months, a standard Census API convention, not a shortcut
specific to this script.

This dataset has no explicit "land" or "truck" value field: only General
(GEN, the total), Air (AIR), Vessel (VES), and Containerized-vessel (CNT, a
subset of VES). Land-border and any other non-air/non-vessel mode is
reported here as the residual GEN - AIR - VES, and labelled as such:
inferred, not measured directly.

Two API gotchas, found by running this against the real endpoint (see
verification_round2.md task 3 for the full trail):
  1. Comma-joined I_COMMODITY (batching multiple codes in one call, the way
     Comtrade's cmdCode works) returns HTTP 204 here, not supported. Each
     code is pulled in its own call instead, over a full 2018-2025 time
     range rather than looping per year.
  2. Rows come back mixing real per-country/per-port detail (SUMMARY_LVL=
     'DET') with overlapping regional/grand-total rows (SUMMARY_LVL='CGP':
     "ASIA", "EUROPEAN UNION", etc.), AND the true grand-total row itself
     (CTY_CODE or PORT == "-") is *also* tagged 'DET' rather than 'CGP'.
     Summing without filtering both out overcounts by roughly 2-6x.
     _december_detail_rows() below does the filtering; skip it and every
     downstream share/reconciliation number is wrong.

This is a spike: read-only, no dbt/Postgres, does not touch ingest/comtrade.py
(which doesn't exist yet) or verification_round1.py.

Usage: .venv/bin/python analysis/census_mot_spike.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import require_census_api_key  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"
METRICS_PATH = REPO_ROOT / "data" / "raw" / "census_mot_spike_metrics.json"
CORRECTIONS_METRICS_PATH = REPO_ROOT / "data" / "raw" / "census_mot_corrections_metrics.json"

HS_URL = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
PORTHS_URL = "https://api.census.gov/data/timeseries/intltrade/imports/porths"

YEARS = list(range(2018, 2026))  # 2018 to 2025 inclusive
AIR_SHARE_FLAG_THRESHOLD = 0.20

# The 22 HS6 codes confirmed against the live HS2017 (H5) list in
# analysis/verification_round1.py / analysis/verification_round1_findings.md.
CANDIDATE_CODES = [
    "280530", "284610", "284690",
    "848610", "848620", "848630", "848640", "848690",
    "850511",
    "854110", "854121", "854129", "854130", "854140", "854150", "854160", "854190",
    "854231", "854232", "854233", "854239", "854290",
]

# Ports are classified by matching keywords against PORT_NAME (a readable
# string like "Los Angeles, CA"), not by parsing the numeric PORT code.
# CBP port codes don't cleanly encode region the way a first-N-digits scheme
# would suggest, and a name match is self-documenting and easy to audit.
# Coverage is deliberately not exhaustive: anything that matches nothing
# below falls into "Unclassified" and is reported explicitly in the
# findings rather than force-fitted or silently dropped.
REGION_KEYWORDS = {
    "West Coast": [
        "LOS ANGELES", "LONG BEACH", "OAKLAND", "SAN FRANCISCO", "SEATTLE",
        "TACOMA", "PORTLAND, OR", "SAN DIEGO", "HONOLULU", "ANCHORAGE",
        ", CA", ", WA", ", OR", ", HI", ", AK",
    ],
    "East Coast": [
        "NEW YORK", "NEWARK", "BOSTON", "BALTIMORE", "NORFOLK",
        "PHILADELPHIA", "CHARLESTON", "SAVANNAH", "MIAMI", "JACKSONVILLE",
        "WILMINGTON, NC", "WILMINGTON, DE", "SAN JUAN", "PORTLAND, ME",
        ", NY", ", NJ", ", MA", ", MD", ", VA", ", PA", ", SC", ", GA",
        ", FL", ", NC", ", DE", ", ME", ", CT", ", RI", ", PR",
    ],
    "Gulf": [
        "HOUSTON", "NEW ORLEANS", "MOBILE", "TAMPA", "PORT ARTHUR",
        "CORPUS CHRISTI", "GULFPORT", "GALVESTON", ", TX", ", LA", ", AL", ", MS",
    ],
    "Land border": [
        "EL PASO", "LAREDO", "NOGALES", "DETROIT", "BUFFALO", "PORT HURON",
        "CHAMPLAIN", "PEMBINA", "BLAINE", "INTERNATIONAL FALLS",
        "GREAT FALLS", "CALEXICO", "NOGALES", "EAGLE PASS", "HIDALGO",
        "BROWNSVILLE",
    ],
}


def region_for_port(port_name: str) -> str:
    name = (port_name or "").upper()
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            return region
    return "Unclassified"


# --------------------------------------------------------------------------
# Corrections (see verification_round2.md "Corrections" section): PORT_NAME
# keyword matching above put land-border crossings like Otay Mesa in
# "Unclassified": their PORT_NAME strings don't reliably contain a state
# abbreviation or a matched city keyword the way "Los Angeles, CA" does, and
# nothing in that scheme could tell a real coastal seaport apart from an
# inland examination station that happens to share a district with one.
#
# This classifier instead uses the official Census/CBP Schedule D port list
# (https://www.census.gov/foreign-trade/schedules/d/dist2.txt, cached at
# data/raw/census_schedule_d_ports.txt), keyed by the 4-digit PORT code the
# API actually returns. Classification is by CBP customs district (the
# code's first two digits) with explicit per-port overrides for the small
# number of districts that mix a coastal seaport with land-border crossings
# under the same district number:
#   - District 25 (San Diego): the seaport itself is West Coast, but
#     Andrade/Calexico/Otay Mesa/San Ysidro/Tecate under the same district
#     are Mexico land crossings.
#   - District 30 (Seattle): the seaport and airport are West Coast, but
#     Blaine/Sumas/Lynden/Oroville/Nighthawk/Danville/Ferry/Laurier/
#     Boundary/Point Roberts/Metaline Falls are Canada land crossings.
#   - District 38 (Detroit): Detroit/Port Huron/Sault Ste. Marie are Canada
#     land crossings; the airports (Detroit Metro, Oakland/Pontiac, Capital
#     Region, Willow Run) and the Great Lakes shipping towns (Saginaw,
#     Escanaba, Marquette, Presque Isle, Rogers City, Algonac, Grand Haven,
#     Muskegon, Alpena, DeTour) are neither coastal ocean ports nor land
#     crossings, and fall to "Interior/other".
# Every other district is either unambiguously coastal or unambiguously a
# land/interior district judged from its own official name (e.g. district 23
# Laredo, TX is entirely a land-border district; there is no Laredo seaport).
# Districts 59 ("Norfolk/Mobile/Charleston", a combined legacy code mixing
# East Coast and Gulf), 60/70/80 (non-geographic: vessels under their own
# power, low-value shipments, export-only mail) are excluded rather than
# guessed at.

DISTRICT_REGION = {
    "01": "East Coast", "02": "Land border", "04": "East Coast",
    "05": "East Coast", "07": "Land border", "09": "Land border",
    "10": "East Coast", "11": "East Coast", "13": "East Coast",
    "14": "East Coast", "15": "East Coast", "16": "East Coast",
    "17": "East Coast", "18": "Gulf", "19": "Gulf", "20": "Gulf",
    "21": "Gulf", "23": "Land border", "24": "Land border",
    "25": "West Coast", "26": "Land border", "27": "West Coast",
    "28": "West Coast", "29": "West Coast", "30": "West Coast",
    "31": "West Coast", "32": "West Coast", "33": "Land border",
    "34": "Land border", "35": "Interior/other", "36": "Land border",
    "37": "Interior/other", "38": "Land border", "39": "Interior/other",
    "41": "Interior/other", "45": "Interior/other", "49": "East Coast",
    "51": "East Coast", "52": "East Coast", "53": "Gulf",
    "54": "East Coast", "55": "Interior/other",
}
NON_GEOGRAPHIC_DISTRICTS = {"59", "60", "70", "80"}

PORT_OVERRIDES = {
    # District 25 (San Diego): Mexico land crossings
    "2502": "Land border",  # Andrade, CA
    "2503": "Land border",  # Calexico, CA
    "2507": "Land border",  # Calexico-East
    "2504": "Land border",  # San Ysidro
    "2505": "Land border",  # Tecate, CA
    "2506": "Land border",  # Otay Mesa
    # District 30 (Seattle): Canada land crossings
    "3004": "Land border",  # Blaine, WA
    "3009": "Land border",  # Sumas, WA
    "3023": "Land border",  # Lynden, WA
    "3019": "Land border",  # Oroville, WA
    "3011": "Land border",  # Nighthawk, WA
    "3012": "Land border",  # Danville, WA
    "3013": "Land border",  # Ferry, WA
    "3016": "Land border",  # Laurier, WA
    "3015": "Land border",  # Boundary, WA
    "3017": "Land border",  # Point Roberts, WA
    "3025": "Land border",  # Metaline Falls
    # District 38 (Detroit): airports and Great Lakes shipping towns are
    # neither coastal-ocean nor land-border; Detroit/Port Huron/Sault Ste.
    # Marie (not listed here) keep the district default of Land border.
    "3807": "Interior/other",  # Detroit Metro Airport
    "3881": "Interior/other",  # Oakland/Pontiac Airport
    "3883": "Interior/other",  # Capital Region Intl Airport, Lansing
    "3882": "Interior/other",  # Willow Run Airport
    "3804": "Interior/other",  # Saginaw/Bay City (Great Lakes)
    "3808": "Interior/other",  # Escanaba (Great Lakes)
    "3809": "Interior/other",  # Marquette (Great Lakes)
    "3842": "Interior/other",  # Presque Isle (Great Lakes)
    "3818": "Interior/other",  # Rogers City (Great Lakes)
    "3814": "Interior/other",  # Algonac (Great Lakes)
    "3816": "Interior/other",  # Grand Haven (Great Lakes)
    "3815": "Interior/other",  # Muskegon (Great Lakes)
    "3843": "Interior/other",  # Alpena (Great Lakes)
    "3819": "Interior/other",  # DeTour (Great Lakes)
}


def official_region_for_port_code(port_code: str) -> str:
    code = str(port_code)
    if code == "-":
        return "Total (excluded)"
    if code in PORT_OVERRIDES:
        return PORT_OVERRIDES[code]
    district = code[:2]
    if district in NON_GEOGRAPHIC_DISTRICTS:
        return "Non-geographic (excluded)"
    return DISTRICT_REGION.get(district, "Unclassified")


def _fetch_json(cache_name: str, url: str, params: dict) -> list:
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    api_key = params.get("key", "")
    resp = requests.get(url, params=params, timeout=120)
    # Census puts the key in the query string (no header-auth option), and
    # error bodies/URLs can echo the full request back, so redact before this
    # ever reaches an exception message, a log, or stdout.
    safe_text = resp.text[:500].replace(api_key, "***REDACTED***") if api_key else resp.text[:500]
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"Census API returned HTTP {resp.status_code} for {cache_name}. "
            "CENSUS_API_KEY may be invalid. Nothing written to disk for this call."
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Census API call for {cache_name} failed: HTTP {resp.status_code}: "
            f"{safe_text}"
        )
    payload = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload))
    time.sleep(0.5)
    return payload


def rows_from_payload(payload: list) -> list[dict]:
    """Census returns [header_row, *data_rows]; convert to list of dicts."""
    header, *data = payload
    return [dict(zip(header, row)) for row in data]


def to_float(v) -> float:
    return 0.0 if v is None else float(v)


TIME_RANGE = f"from {YEARS[0]}-01 to {YEARS[-1]}-12"


def _december_detail_rows(payload: list) -> list[dict]:
    """Keep only December rows (year-end YTD == full calendar year total),
    only SUMMARY_LVL='DET' rows, and drop the '-' grand-total sentinel row.

    Two layers of aggregate rows turned up, both needing exclusion:

    1. SUMMARY_LVL='CGP' rows: overlapping regional/grouping totals
       ("ASIA", "EUROPEAN UNION", "PACIFIC RIM COUNTRIES", "USMCA (NAFTA)",
       etc.) that double- and triple-count individual countries. Excluded by
       requiring SUMMARY_LVL == 'DET'.
    2. A "TOTAL FOR ALL COUNTRIES" / "TOTAL FOR ALL PORTS" row that is
       *itself* tagged SUMMARY_LVL='DET' (CTY_CODE or PORT == '-',
       SUMMARY_LVL2='HS' instead of the real rows' 'HSCY'). Summing DET
       rows without excluding this sentinel silently doubles the total,
       since this one row's value already equals the sum of every other DET
       row. Confirmed live: for HS 854231 / 2018, the 96 real DET country
       rows summed to $21,556,458,087, and the CTY_CODE='-' row's own value
       was also exactly $21,556,458,087. That number reconciles to
       Comtrade's cached $21,619,335,521 for the same code/year within
       0.29%. Excluded by dropping CTY_CODE == '-' / PORT == '-'.
    """
    rows = rows_from_payload(payload)
    out = []
    for r in rows:
        t = r.get("time", "")
        is_total_sentinel = r.get("CTY_CODE") == "-" or r.get("PORT") == "-"
        if t.endswith("-12") and r.get("SUMMARY_LVL") == "DET" and not is_total_sentinel:
            r["year"] = int(t[:4])
            out.append(r)
    return out


def pull_hs_annual(api_key: str) -> list[dict]:
    """imports/hs, per code (comma-joined I_COMMODITY returns 204, doesn't
    work for this endpoint, confirmed live), full 2018-2025 monthly range in
    one call per code, keeping December (year-to-date), detail-only rows."""
    all_rows = []
    for code in CANDIDATE_CODES:
        payload = _fetch_json(
            f"census_hs_annual_{code}.json",
            HS_URL,
            params={
                "get": "I_COMMODITY,CTY_CODE,CTY_NAME,SUMMARY_LVL,GEN_VAL_YR,AIR_VAL_YR,VES_VAL_YR,CNT_VAL_YR",
                "COMM_LVL": "HS6",
                "I_COMMODITY": code,
                "time": TIME_RANGE,
                "key": api_key,
            },
        )
        all_rows.extend(_december_detail_rows(payload))
    return all_rows


def pull_porths_annual(api_key: str) -> list[dict]:
    """imports/porths, per code, same full-range-then-filter approach."""
    all_rows = []
    for code in CANDIDATE_CODES:
        payload = _fetch_json(
            f"census_porths_annual_{code}.json",
            PORTHS_URL,
            params={
                "get": "I_COMMODITY,PORT,PORT_NAME,SUMMARY_LVL,GEN_VAL_YR",
                "COMM_LVL": "HS6",
                "I_COMMODITY": code,
                "time": TIME_RANGE,
                "key": api_key,
            },
        )
        all_rows.extend(_december_detail_rows(payload))
    return all_rows


def pull_porths_vessel_annual(api_key: str) -> list[dict]:
    """imports/porths with VES_VAL_YR added, for the corrected vessel-only
    port-of-entry table (see verification_round2.md "Corrections"). Separate
    cache files from pull_porths_annual's (GEN_VAL_YR only) so the original,
    already-published numbers stay reproducible from their own cache."""
    all_rows = []
    for code in CANDIDATE_CODES:
        payload = _fetch_json(
            f"census_porths_vessel_{code}.json",
            PORTHS_URL,
            params={
                "get": "I_COMMODITY,PORT,PORT_NAME,SUMMARY_LVL,GEN_VAL_YR,VES_VAL_YR",
                "COMM_LVL": "HS6",
                "I_COMMODITY": code,
                "time": TIME_RANGE,
                "key": api_key,
            },
        )
        all_rows.extend(_december_detail_rows(payload))
    return all_rows


def compute_vessel_port_region_distribution(porths_vessel_rows: list[dict]) -> dict:
    """Per code, per year: share of VESSEL value (not total value) entering
    West Coast / East Coast / Gulf, using the official Schedule D port-code
    classifier. Land border, Interior/other, and Non-geographic buckets are
    computed too (as a QA check, ships shouldn't be arriving at a land
    crossing) but are not part of the three columns the corrections asked for.
    """
    totals = defaultdict(lambda: defaultdict(float))
    for r in porths_vessel_rows:
        key = (r["I_COMMODITY"], r["year"])
        region = official_region_for_port_code(r["PORT"])
        totals[key][region] += to_float(r.get("VES_VAL_YR"))

    per_code_year = {}
    for (code, year), regions in totals.items():
        total_ves = sum(regions.values())
        per_code_year[(code, year)] = {
            "total_vessel_value": total_ves,
            "west_coast_share": regions.get("West Coast", 0.0) / total_ves if total_ves else None,
            "east_coast_share": regions.get("East Coast", 0.0) / total_ves if total_ves else None,
            "gulf_share": regions.get("Gulf", 0.0) / total_ves if total_ves else None,
            "land_border_share": regions.get("Land border", 0.0) / total_ves if total_ves else None,
            "other_share": (
                (regions.get("Interior/other", 0.0) + regions.get("Unclassified", 0.0))
                / total_ves if total_ves else None
            ),
        }
    return per_code_year


def compute_official_land_border_share_of_gen(porths_rows: list[dict]) -> dict:
    """Per code: share of TOTAL (GEN_VAL_YR) import value entering through an
    officially-classified land-border port, using the same Schedule D
    classifier, for comparing against the mode-table residual (see
    "Corrections" in verification_round2.md). Reuses the original
    GEN_VAL_YR-only porths pull (pull_porths_annual), just with the better
    classifier applied instead of the old PORT_NAME keyword match."""
    totals = defaultdict(lambda: defaultdict(float))
    for r in porths_rows:
        code = r["I_COMMODITY"]
        region = official_region_for_port_code(r["PORT"])
        totals[code][region] += to_float(r.get("GEN_VAL_YR"))

    result = {}
    for code, regions in totals.items():
        total_gen = sum(regions.values())
        result[code] = {
            "total_gen": total_gen,
            "land_border_share": regions.get("Land border", 0.0) / total_gen if total_gen else None,
        }
    return result


def compute_residual_by_country(hs_rows: list[dict]) -> dict:
    """Per code: split the mode-table residual (GEN - AIR - VES) by whether
    it comes from Mexico/Canada (land-eligible) or every other country (not
    land-eligible: there is no other US land border). If the residual is
    genuinely land trade, it should be concentrated in Mexico/Canada; if it's
    spread across non-adjacent countries, it isn't land."""
    totals = defaultdict(lambda: defaultdict(float))
    for r in hs_rows:
        code = r["I_COMMODITY"]
        name = (r.get("CTY_NAME") or "").upper()
        is_land_eligible = "CANADA" in name or "MEXICO" in name
        gen = to_float(r.get("GEN_VAL_YR"))
        air = to_float(r.get("AIR_VAL_YR"))
        ves = to_float(r.get("VES_VAL_YR"))
        residual = gen - air - ves
        bucket = "mexico_canada" if is_land_eligible else "rest_of_world"
        totals[code]["gen_total"] += gen
        totals[code][f"residual_{bucket}"] += residual
        totals[code]["residual_total"] += residual

    result = {}
    for code, t in totals.items():
        resid_total = t["residual_total"]
        gen_total = t["gen_total"]
        result[code] = {
            "gen_total": gen_total,
            "residual_total": resid_total,
            "residual_share_of_gen": resid_total / gen_total if gen_total else None,
            "residual_from_mexico_canada": t.get("residual_mexico_canada", 0.0),
            "residual_from_rest_of_world": t.get("residual_rest_of_world", 0.0),
            "pct_of_residual_from_mexico_canada": (
                t.get("residual_mexico_canada", 0.0) / resid_total if resid_total else None
            ),
        }
    return result


def check_porths_has_partner_country(api_key: str) -> tuple[bool, list[dict]]:
    """Confirmatory single-code pull with CTY_CODE/CTY_NAME requested."""
    payload = _fetch_json(
        "census_porths_partner_check_854231_2023.json",
        PORTHS_URL,
        params={
            "get": "I_COMMODITY,PORT,PORT_NAME,CTY_CODE,CTY_NAME,GEN_VAL_YR",
            "COMM_LVL": "HS6",
            "I_COMMODITY": "854231",
            "time": "2023-12",
            "key": api_key,
        },
    )
    rows = rows_from_payload(payload)
    has_real_country_values = any(
        r.get("CTY_NAME") not in (None, "", "0") for r in rows
    )
    return has_real_country_values, rows[:5]


def load_comtrade_world_values() -> dict[tuple[str, int], float]:
    """code,year -> Comtrade partnerCode=0 (World) primaryValue, from the
    cached verification_round1.py pulls (2018-2021 only, H5-native years)."""
    values: dict[tuple[str, int], float] = {}
    for year in (2018, 2019, 2020, 2021):
        cache_file = CACHE_DIR / f"comtrade_final_C_A_HS_{year}.json"
        if not cache_file.exists():
            continue
        payload = json.loads(cache_file.read_text())
        for row in payload.get("data", []):
            if row.get("partnerCode") == 0 and row["cmdCode"] in CANDIDATE_CODES:
                values[(row["cmdCode"], year)] = row["primaryValue"]
    return values


def compute_mode_shares(hs_rows: list[dict]) -> dict:
    """Per code, per year: sum across all countries, then air/vessel/other share."""
    totals = defaultdict(lambda: defaultdict(float))
    for r in hs_rows:
        key = (r["I_COMMODITY"], r["year"])
        totals[key]["gen"] += to_float(r.get("GEN_VAL_YR"))
        totals[key]["air"] += to_float(r.get("AIR_VAL_YR"))
        totals[key]["ves"] += to_float(r.get("VES_VAL_YR"))
        totals[key]["cnt"] += to_float(r.get("CNT_VAL_YR"))

    per_code_year = {}
    for (code, year), t in totals.items():
        gen = t["gen"]
        per_code_year[(code, year)] = {
            "gen": gen,
            "air_share": t["air"] / gen if gen else None,
            "vessel_share": t["ves"] / gen if gen else None,
            "containerized_share": t["cnt"] / gen if gen else None,
            "other_share": (gen - t["air"] - t["ves"]) / gen if gen else None,
        }

    # overall (2018-2025 combined) share per code, for the >20% air flag
    code_overall = defaultdict(lambda: defaultdict(float))
    for (code, year), t in totals.items():
        code_overall[code]["gen"] += t["gen"]
        code_overall[code]["air"] += t["air"]
        code_overall[code]["ves"] += t["ves"]
    overall = {}
    for code, t in code_overall.items():
        gen = t["gen"]
        overall[code] = {
            "gen": gen,
            "air_share": t["air"] / gen if gen else None,
            "vessel_share": t["ves"] / gen if gen else None,
            "other_share": (gen - t["air"] - t["ves"]) / gen if gen else None,
        }
    return {"per_code_year": per_code_year, "overall": overall}


def compute_port_region_distribution(porths_rows: list[dict]) -> dict:
    per_code = defaultdict(lambda: defaultdict(float))
    unclassified_names = set()
    for r in porths_rows:
        code = r["I_COMMODITY"]
        region = region_for_port(r.get("PORT_NAME"))
        if region == "Unclassified":
            unclassified_names.add(r.get("PORT_NAME"))
        per_code[code][region] += to_float(r.get("GEN_VAL_YR"))

    result = {}
    for code, regions in per_code.items():
        total = sum(regions.values())
        result[code] = {
            "total": total,
            "shares": {
                region: (val / total if total else None)
                for region, val in regions.items()
            },
        }
    return {"per_code": result, "unclassified_port_names": sorted(n for n in unclassified_names if n)}


def compute_reconciliation(hs_rows: list[dict], comtrade_values: dict) -> dict:
    census_world = defaultdict(float)
    for r in hs_rows:
        census_world[(r["I_COMMODITY"], r["year"])] += to_float(r.get("GEN_VAL_YR"))

    reconciliation = {}
    gaps_pct = []
    for (code, year), comtrade_val in comtrade_values.items():
        census_val = census_world.get((code, year))
        if census_val is None or comtrade_val == 0:
            continue
        gap_pct = (census_val - comtrade_val) / comtrade_val
        reconciliation[f"{code}|{year}"] = {
            "census_value": census_val,
            "comtrade_value": comtrade_val,
            "gap_pct": gap_pct,
        }
        gaps_pct.append(gap_pct)

    summary = {}
    if gaps_pct:
        summary = {
            "n": len(gaps_pct),
            "mean_gap_pct": sum(gaps_pct) / len(gaps_pct),
            "min_gap_pct": min(gaps_pct),
            "max_gap_pct": max(gaps_pct),
        }
    return {"detail": reconciliation, "summary": summary}


def compute_mexico_canada_mode(hs_rows: list[dict]) -> dict:
    result = {}
    for country_key in ("CANADA", "MEXICO"):
        totals = defaultdict(float)
        for r in hs_rows:
            name = (r.get("CTY_NAME") or "").upper()
            if country_key in name:
                totals["gen"] += to_float(r.get("GEN_VAL_YR"))
                totals["air"] += to_float(r.get("AIR_VAL_YR"))
                totals["ves"] += to_float(r.get("VES_VAL_YR"))
        gen = totals["gen"]
        result[country_key] = {
            "gen": gen,
            "air_share": totals["air"] / gen if gen else None,
            "vessel_share": totals["ves"] / gen if gen else None,
            "land_or_other_share": (gen - totals["air"] - totals["ves"]) / gen if gen else None,
        }
    return result


def main() -> None:
    api_key = require_census_api_key()

    print("Pulling Census imports/hs (annual, all codes x all countries)...")
    hs_rows = pull_hs_annual(api_key)
    print(f"  {len(hs_rows)} rows")

    print("Pulling Census imports/porths (annual, all codes x all ports)...")
    porths_rows = pull_porths_annual(api_key)
    print(f"  {len(porths_rows)} rows")

    print("Checking whether imports/porths carries partner country...")
    has_partner, partner_sample = check_porths_has_partner_country(api_key)
    print(f"  porths carries partner country: {has_partner}")

    print("Loading cached Comtrade world values for reconciliation...")
    comtrade_values = load_comtrade_world_values()
    print(f"  {len(comtrade_values)} code-year Comtrade values available")

    mode_shares = compute_mode_shares(hs_rows)
    port_regions = compute_port_region_distribution(porths_rows)
    reconciliation = compute_reconciliation(hs_rows, comtrade_values)
    mx_ca = compute_mexico_canada_mode(hs_rows)

    flagged = {
        code: v["air_share"]
        for code, v in mode_shares["overall"].items()
        if v["air_share"] is not None and v["air_share"] > AIR_SHARE_FLAG_THRESHOLD
    }
    print()
    print(f"Codes with overall air share > {AIR_SHARE_FLAG_THRESHOLD:.0%}: {flagged}")
    print()
    print("Reconciliation summary:", reconciliation["summary"])
    print()
    print("Mexico / Canada mode split:", mx_ca)
    print()
    print("Unclassified port names (expand REGION_KEYWORDS if this is non-empty):")
    print(" ", port_regions["unclassified_port_names"])

    metrics = {
        "mode_shares_overall": mode_shares["overall"],
        "mode_shares_per_code_year": {
            f"{code}|{year}": v for (code, year), v in mode_shares["per_code_year"].items()
        },
        "port_region_distribution": port_regions,
        "reconciliation": reconciliation,
        "mexico_canada_mode": mx_ca,
        "porths_has_partner_country": has_partner,
        "porths_partner_sample": partner_sample,
        "air_share_flagged_codes": flagged,
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print()
    print(f"Computed metrics written to {METRICS_PATH.relative_to(REPO_ROOT)}")

    # --- Corrections: vessel-only port table + residual investigation ---
    print()
    print("=== Corrections ===")
    print("Pulling Census imports/porths with VES_VAL_YR (vessel-only table)...")
    porths_vessel_rows = pull_porths_vessel_annual(api_key)
    print(f"  {len(porths_vessel_rows)} rows")

    vessel_region_by_year = compute_vessel_port_region_distribution(porths_vessel_rows)
    official_land_border = compute_official_land_border_share_of_gen(porths_rows)
    residual_by_country = compute_residual_by_country(hs_rows)

    print()
    print("Vessel-value region share, sample (854231):")
    for (code, year), v in sorted(vessel_region_by_year.items()):
        if code == "854231":
            print(f"  {year}: west={v['west_coast_share']}, east={v['east_coast_share']}, "
                  f"gulf={v['gulf_share']}, land={v['land_border_share']}, other={v['other_share']}")

    print()
    print("Official land-border share of GEN_VAL, per code:")
    for code, v in sorted(official_land_border.items()):
        print(f"  {code}: {v['land_border_share']}")

    print()
    print("Residual composition by country, per code:")
    for code, v in sorted(residual_by_country.items()):
        print(f"  {code}: residual={v['residual_share_of_gen']}, "
              f"pct_from_mexico_canada={v['pct_of_residual_from_mexico_canada']}")

    corrections_metrics = {
        "vessel_port_region_by_code_year": {
            f"{code}|{year}": v for (code, year), v in vessel_region_by_year.items()
        },
        "official_land_border_share_of_gen": official_land_border,
        "residual_by_country": residual_by_country,
    }
    CORRECTIONS_METRICS_PATH.write_text(json.dumps(corrections_metrics, indent=2))
    print()
    print(f"Corrections metrics written to {CORRECTIONS_METRICS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
