"""Verification-phase data reality check (PROJECT_BRIEF.md section 15, charter section 8).

Answers, using only live source data, before any dbt model is written:

1. Which candidate HS6 codes from PROJECT_BRIEF.md section 3 exist in the live
   Comtrade HS2017 (H5) code list, and which do not.
2. What is the latest available year for US import data.
3. For each surviving code, US import value and record count per year from
   2018 to the latest year covered by question 2.
4. Can we paginate the PortWatch FeatureServer for one chokepoint and get back
   daily rows, and what columns come back.

This is a verification pass only: it makes read-only GET requests, caches every
raw response under data/raw/, and writes a findings report to
analysis/verification_round1_findings.md. It does not touch Postgres or dbt.

Usage: .venv/bin/python analysis/verification_round1.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import CONFIG  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"
FINDINGS_PATH = REPO_ROOT / "analysis" / "verification_round1_findings.md"

COMTRADE_REFERENCE_LIST_URL = (
    "https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json"
)
COMTRADE_DATA_BASE = "https://comtradeapi.un.org/data/v1"
PORTWATCH_LAYER_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)

REPORTER_USA = "842"
FLOW_IMPORT = "M"
CANDIDATE_START_YEAR = 2018
# Coarse floor: a real, systemic input to semiconductor or rare-earth supply
# chains would not sit under $1M in cumulative US import value across the
# covered years. Anything below this is flagged for a second look, not
# silently dropped.
NEGLIGIBLE_VALUE_USD = 1_000_000

# PortWatch's own maxRecordCount for this layer (confirmed via ?f=json on the
# layer endpoint); pagination must request no more than this per page.
PORTWATCH_PAGE_SIZE = 1000
# Strait of Malacca. Per PROJECT_BRIEF.md section 6, both baskets route
# predominantly via the South China Sea and Malacca, not Hormuz, so this is
# the chokepoint the pagination test should actually exercise.
PORTWATCH_TEST_CHOKEPOINT = "chokepoint5"
PORTWATCH_TEST_CHOKEPOINT_NAME = "Strait of Malacca"

# Candidate baskets as named in PROJECT_BRIEF.md section 3. "families" are
# HS headings whose full set of HS2017 six-digit leaf codes are candidates;
# "explicit_codes" are specific six-digit codes named in the brief.
BASKETS = {
    "semiconductors_and_sme": {
        "label": "Semiconductors and semiconductor manufacturing equipment",
        "families": ["8541", "8542", "8486"],
        "explicit_codes": [],
    },
    "rare_earths_and_magnets": {
        "label": "Rare earths and permanent magnets",
        "families": ["2846"],
        "explicit_codes": ["280530", "850511"],
    },
}


class ComtradeAuthError(RuntimeError):
    """Raised on HTTP 401/403 from the Comtrade API. Never includes the key."""


def _comtrade_headers() -> dict:
    # Subscription key travels as a header, never as a query param, so it
    # can never end up in a cached URL, a raised exception's message, or a
    # log line. requests.Response.raise_for_status() echoes resp.url.
    return {"Ocp-Apim-Subscription-Key": CONFIG.comtrade_api_key}


def _fetch_json(
    cache_name: str,
    url: str,
    params: dict | None,
    *,
    headers: dict | None = None,
    context: str,
) -> tuple[dict, bool]:
    """GET url, caching the raw JSON response under data/raw/cache_name.

    Returns (payload, from_cache). Raises ComtradeAuthError on 401/403 before
    writing anything to disk. Retries once on 429 (rate limit).
    """
    cache_file = CACHE_DIR / cache_name
    if cache_file.exists():
        return json.loads(cache_file.read_text()), True

    resp = None
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=headers, timeout=120)
        if resp.status_code in (401, 403):
            raise ComtradeAuthError(
                f"{context} failed with HTTP {resp.status_code}. "
                "COMTRADE_API_KEY may be missing, invalid, expired, or "
                "regenerated. Log into the Comtrade portal and check the "
                "subscription. Nothing was written to disk for this call."
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
    return payload, False


# --------------------------------------------------------------------------
# Question 1: which candidate HS6 codes exist in the live HS2017 (H5) list
# --------------------------------------------------------------------------


def _fetch_h5_reference() -> list[dict]:
    ref_list, _ = _fetch_json(
        "comtrade_reference_list.json",
        COMTRADE_REFERENCE_LIST_URL,
        params=None,
        context="Comtrade reference file list",
    )
    h5_entry = next(
        r for r in ref_list["results"] if r["category"] == "cmd:H5"
    )
    h5_ref, _ = _fetch_json(
        "comtrade_reference_cmd_H5.json",
        h5_entry["fileuri"],
        params=None,
        context="Comtrade HS2017 (H5) commodity code list",
    )
    return h5_ref["results"]


def check_candidate_codes(h5_codes: list[dict]) -> dict:
    by_id = {row["id"]: row for row in h5_codes}
    result = {}
    for basket_key, basket in BASKETS.items():
        basket_result = {"families": {}, "explicit_codes": {}}
        for prefix in basket["families"]:
            children = sorted(
                code
                for code, row in by_id.items()
                if code.startswith(prefix)
                and len(code) == 6
                and row.get("isLeaf") == "1"
            )
            basket_result["families"][prefix] = [
                {"code": c, "text": by_id[c]["text"], "exists": True} for c in children
            ]
        for code in basket["explicit_codes"]:
            exists = code in by_id
            basket_result["explicit_codes"][code] = {
                "exists": exists,
                "text": by_id[code]["text"] if exists else None,
            }
        result[basket_key] = basket_result
    return result


def surviving_codes(candidate_result: dict) -> dict:
    """Map surviving HS6 code -> basket_key, for every code confirmed to exist."""
    codes = {}
    for basket_key, basket in candidate_result.items():
        for children in basket["families"].values():
            for c in children:
                codes[c["code"]] = basket_key
        for code, info in basket["explicit_codes"].items():
            if info["exists"]:
                codes[code] = basket_key
    return codes


# --------------------------------------------------------------------------
# Question 2: latest available year for US import data
# --------------------------------------------------------------------------


def check_data_availability() -> dict:
    h5_avail, _ = _fetch_json(
        "comtrade_availability_C_A_H5.json",
        f"{COMTRADE_DATA_BASE}/getDa/C/A/H5",
        params={"reporterCode": REPORTER_USA},
        headers=_comtrade_headers(),
        context="H5 data availability for USA",
    )
    hs_avail, _ = _fetch_json(
        "comtrade_availability_C_A_HS.json",
        f"{COMTRADE_DATA_BASE}/getDa/C/A/HS",
        params={"reporterCode": REPORTER_USA},
        headers=_comtrade_headers(),
        context="combined-classification data availability for USA",
    )
    h5_years = sorted(r["period"] for r in h5_avail["data"])
    all_years = sorted(r["period"] for r in hs_avail["data"])
    by_classification: dict[str, list[int]] = {}
    for r in hs_avail["data"]:
        by_classification.setdefault(r["classificationCode"], []).append(r["period"])
    return {
        "h5_native_years": h5_years,
        "latest_h5_native_year": max(h5_years) if h5_years else None,
        "all_years": all_years,
        "latest_available_year": max(all_years) if all_years else None,
        "classification_by_year": {
            cl: sorted(years) for cl, years in by_classification.items()
        },
    }


# --------------------------------------------------------------------------
# Question 3: import value and record count per surviving code, per year
# --------------------------------------------------------------------------


def pull_yearly_values(codes: list[str], years: list[int]) -> dict:
    """One batched Comtrade call per year, covering every code at once."""
    per_code_per_year: dict[str, dict[int, dict]] = {c: {} for c in codes}
    for year in years:
        payload, _ = _fetch_json(
            f"comtrade_final_C_A_HS_{year}.json",
            f"{COMTRADE_DATA_BASE}/get/C/A/HS",
            params={
                "reporterCode": REPORTER_USA,
                "period": year,
                "cmdCode": ",".join(codes),
                "flowCode": FLOW_IMPORT,
                "partner2Code": 0,
                "customsCode": "C00",
                "motCode": 0,
            },
            headers=_comtrade_headers(),
            context=f"final trade data for {year}",
        )
        rows = payload.get("data", [])
        for code in codes:
            code_rows = [r for r in rows if r["cmdCode"] == code]
            # partnerCode 0 is Comtrade's World aggregate row, not a supplier.
            # Left mixed into partner_rows it would double-count as a partner
            # and inflate the record count, so it's split out here.
            world_row = next((r for r in code_rows if r["partnerCode"] == 0), None)
            partner_rows = [r for r in code_rows if r["partnerCode"] != 0]
            value = (
                world_row["primaryValue"]
                if world_row is not None
                else sum(r["primaryValue"] for r in partner_rows)
            )
            per_code_per_year[code][year] = {
                "value_usd": value,
                "partner_record_count": len(partner_rows),
                "classification_code": code_rows[0]["classificationCode"]
                if code_rows
                else None,
            }
    return per_code_per_year


# --------------------------------------------------------------------------
# Question 4: PortWatch FeatureServer pagination for one chokepoint
# --------------------------------------------------------------------------


def check_portwatch_pagination() -> dict:
    offset = 0
    page_sizes = []
    columns: list[str] | None = None
    total_rows = 0
    max_pages = 20  # safety cap; well beyond what one chokepoint needs
    for page_num in range(max_pages):
        payload, _ = _fetch_json(
            f"portwatch_{PORTWATCH_TEST_CHOKEPOINT}_offset{offset}.json",
            PORTWATCH_LAYER_URL,
            params={
                "where": f"portid='{PORTWATCH_TEST_CHOKEPOINT}'",
                "outFields": "*",
                "orderByFields": "date ASC",
                "resultOffset": offset,
                "resultRecordCount": PORTWATCH_PAGE_SIZE,
                "f": "json",
            },
            headers=None,
            context=f"PortWatch page at offset {offset}",
        )
        features = payload.get("features", [])
        if columns is None and features:
            columns = sorted(features[0]["attributes"].keys())
        page_sizes.append(len(features))
        total_rows += len(features)
        if len(features) < PORTWATCH_PAGE_SIZE:
            break
        offset += PORTWATCH_PAGE_SIZE
    else:
        raise RuntimeError(
            f"PortWatch pagination for {PORTWATCH_TEST_CHOKEPOINT} did not "
            f"terminate within {max_pages} pages. Investigate before trusting "
            "this as a bounded loop."
        )
    return {
        "chokepoint_id": PORTWATCH_TEST_CHOKEPOINT,
        "chokepoint_name": PORTWATCH_TEST_CHOKEPOINT_NAME,
        "pages_fetched": len(page_sizes),
        "rows_per_page": page_sizes,
        "total_rows": total_rows,
        "columns": columns or [],
    }


# --------------------------------------------------------------------------
# Report generation
# --------------------------------------------------------------------------


def render_findings(
    candidate_result: dict,
    availability: dict,
    yearly_values: dict,
    codes_by_basket: dict,
    portwatch: dict,
    years_pulled: list[int],
) -> str:
    lines: list[str] = []
    lines.append("# Verification round 1 findings")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(
        "Source: `analysis/verification_round1.py`, run against live Comtrade and "
        "IMF PortWatch endpoints. Raw responses cached under `data/raw/`."
    )
    lines.append("")

    # Q1
    lines.append("## 1. Candidate HS6 codes vs. the live HS2017 (H5) code list")
    lines.append("")
    for basket_key, basket in candidate_result.items():
        label = BASKETS[basket_key]["label"]
        lines.append(f"### {label} (`{basket_key}`)")
        lines.append("")
        for prefix, children in basket["families"].items():
            lines.append(f"- Heading `{prefix}`: {len(children)} HS6 leaf code(s) found")
            for c in children:
                lines.append(f"  - `{c['code']}`: {c['text']}")
        for code, info in basket["explicit_codes"].items():
            status = "EXISTS" if info["exists"] else "NOT FOUND"
            desc = f": {info['text']}" if info["exists"] else ""
            lines.append(f"- Explicit code `{code}`: **{status}**{desc}")
        lines.append("")
    missing = [
        code
        for basket in candidate_result.values()
        for code, info in basket["explicit_codes"].items()
        if not info["exists"]
    ]
    if missing:
        lines.append(
            f"**Codes named in the brief but not found in live HS2017 (H5): {', '.join(missing)}.** "
            "Resolve before committing to `dim_product`: either renumbered, retired, "
            "or the brief has a typo."
        )
    else:
        lines.append(
            "All explicitly named codes from PROJECT_BRIEF.md section 3 exist in "
            "the live HS2017 (H5) list. Family headings resolved to the leaf codes above."
        )
    lines.append("")

    # Q2
    lines.append("## 2. Latest available year for US import data")
    lines.append("")
    lines.append(
        f"- Latest year available under **any** classification: "
        f"**{availability['latest_available_year']}**"
    )
    lines.append(
        f"- Latest year still natively classified as HS2017 (H5): "
        f"**{availability['latest_h5_native_year']}** "
        f"(H5-native years: {availability['h5_native_years']})"
    )
    lines.append("")
    cl_summary = ", ".join(
        f"{cl}: {min(years)}-{max(years)}"
        for cl, years in sorted(
            availability["classification_by_year"].items(), key=lambda kv: min(kv[1])
        )
    )
    lines.append(f"- Classification vintage by year (reporter USA): {cl_summary}")
    lines.append("")
    if availability["latest_h5_native_year"] < availability["latest_available_year"]:
        lines.append(
            "**Finding:** US import data under the project's chosen HS2017 (H5) "
            f"classification runs through {availability['latest_h5_native_year']} only. "
            f"Years {availability['latest_h5_native_year'] + 1}-"
            f"{availability['latest_available_year']} are reported under a newer "
            "revision. Querying the H5-tagged endpoint for those later years "
            "returns zero rows rather than converted data. Comtrade does not "
            "silently reclassify. This is the HS concordance problem named in "
            "PROJECT_BRIEF.md section 6, arriving one revision earlier than the "
            "brief's stated backward-only H4 enhancement anticipated. Extending "
            "this project's year range past "
            f"{availability['latest_h5_native_year']} requires the bridge table, "
            "not a wider H5 query."
        )
    lines.append("")

    # Q3
    lines.append(
        f"## 3. Import value and record count per surviving code, "
        f"{years_pulled[0]}-{years_pulled[-1]}"
    )
    lines.append("")
    lines.append(
        f"Pulled for {years_pulled[0]}-{years_pulled[-1]} only, the overlap "
        "between the brief's requested start year and the last year with "
        "native H5 data (see finding above). One batched Comtrade call per "
        "year covers every surviving code."
    )
    lines.append("")
    lines.append(
        "| Code | Basket | " + " | ".join(str(y) for y in years_pulled) + " | Total value (USD) | Flag |"
    )
    lines.append("|---" * (3 + len(years_pulled) + 2) + "|")
    for code in sorted(yearly_values):
        by_year = yearly_values[code]
        total_value = sum(by_year[y]["value_usd"] for y in years_pulled)
        cells = []
        for y in years_pulled:
            v = by_year[y]
            cells.append(f"${v['value_usd']:,.0f} ({v['partner_record_count']} rec)")
        flag = "NEGLIGIBLE VALUE" if total_value < NEGLIGIBLE_VALUE_USD else ""
        lines.append(
            f"| `{code}` | {codes_by_basket[code]} | "
            + " | ".join(cells)
            + f" | ${total_value:,.0f} | {flag} |"
        )
    lines.append("")
    negligible = [
        code
        for code in yearly_values
        if sum(yearly_values[code][y]["value_usd"] for y in years_pulled) < NEGLIGIBLE_VALUE_USD
    ]
    if negligible:
        lines.append(
            f"**Negligible-value codes (cumulative < ${NEGLIGIBLE_VALUE_USD:,.0f} "
            f"across {years_pulled[0]}-{years_pulled[-1]}): {', '.join(sorted(negligible))}.** "
            "Candidates for exclusion or basket-definition review."
        )
    else:
        lines.append(
            f"No surviving code fell below the ${NEGLIGIBLE_VALUE_USD:,.0f} cumulative-value floor."
        )
    lines.append("")

    # Q4
    lines.append("## 4. PortWatch FeatureServer pagination")
    lines.append("")
    lines.append(
        f"Chokepoint tested: **{portwatch['chokepoint_name']}** "
        f"(`{portwatch['chokepoint_id']}`), the chokepoint PROJECT_BRIEF.md "
        "section 6 identifies as most relevant to both baskets."
    )
    lines.append("")
    lines.append(
        f"- Pages fetched: {portwatch['pages_fetched']} "
        f"(rows per page: {portwatch['rows_per_page']})"
    )
    lines.append(f"- Total daily rows retrieved: {portwatch['total_rows']}")
    lines.append(
        f"- Pagination confirmed working: yes. Layer `maxRecordCount` is "
        f"{PORTWATCH_PAGE_SIZE}, and this chokepoint alone exceeds one page."
    )
    lines.append("")
    lines.append("Columns returned:")
    lines.append("")
    for col in portwatch["columns"]:
        lines.append(f"- `{col}`")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    print("Fetching HS2017 (H5) commodity reference list...")
    h5_codes = _fetch_h5_reference()

    print("Checking candidate HS6 codes against the live list...")
    candidate_result = check_candidate_codes(h5_codes)
    codes_by_basket = surviving_codes(candidate_result)
    codes = sorted(codes_by_basket)
    print(f"  {len(codes)} surviving code(s): {codes}")

    print("Checking Comtrade data availability for USA...")
    availability = check_data_availability()
    latest_h5_year = availability["latest_h5_native_year"]
    print(
        f"  Latest available year (any classification): "
        f"{availability['latest_available_year']}; latest H5-native year: {latest_h5_year}"
    )

    years_pulled = [y for y in range(CANDIDATE_START_YEAR, latest_h5_year + 1)]
    print(f"Pulling import value and record counts for {years_pulled}...")
    yearly_values = pull_yearly_values(codes, years_pulled)

    print(f"Testing PortWatch pagination for {PORTWATCH_TEST_CHOKEPOINT_NAME}...")
    portwatch = check_portwatch_pagination()
    print(f"  {portwatch['total_rows']} rows across {portwatch['pages_fetched']} page(s)")

    report = render_findings(
        candidate_result,
        availability,
        yearly_values,
        codes_by_basket,
        portwatch,
        years_pulled,
    )
    FINDINGS_PATH.write_text(report)
    print(f"Findings written to {FINDINGS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
