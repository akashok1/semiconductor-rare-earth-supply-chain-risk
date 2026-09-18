"""HS classification bridge: canonical products across the HS2017/HS2022 split.

US import data is native H5 (HS2017) through 2021 and H6 (HS2022) from 2022
onward (see CLAUDE.md, "The core architectural rule"). A canonical product
must map to every HS6 code that ever represented it, across classification
vintages, so marts can group by `canonical_product_id` instead of raw HS
code. This module builds that bridge for the 22 candidate codes verified in
`analysis/verification_round1_findings.md` (the live HS2017 leaf-code check)
and `analysis/verification_round2.md` (the Census mode-of-transport spike,
which independently confirmed 854140/854150 have no 2022+ data).

Source of truth for the HS2017-to-HS2022 correlation itself is the UN Stats
correlation table (unstats.un.org/unsd/classifications/Econ), not guesswork:
`HS2022toHS2017ConversionAndCorrelationTables.xlsx`, cached under
`data/raw/`. That workbook ships two tabs, read together:

- "HS2022-HS2017 Conversions": exactly one row per current HS2022 code,
  naming the single HS2017 code the WCO treats as its predecessor. A code
  retired in HS2022 with nothing claiming it as predecessor here simply
  never appears in this tab. This is the candidate-successor list.
- "HS2022-HS2017 Correlations": every HS2022/HS2017 code pair that overlaps
  at all (thousands more rows than Conversions), each tagged with a
  relationship type (1:1, n:1, 1:n, n:n). Heading 8549 ("electrical and
  electronic waste and scrap", new in HS2022) shows up as an n:n predecessor
  of nearly every old code in this bridge, and 8524 ("flat panel display
  modules", also new in HS2022) does the same to the 8486 subset, so this
  tab alone is too noisy to resolve against directly. Used here only to
  look up the relationship tag for the specific (new, old) pairs Conversions
  already named as candidates.

A code's forward mapping is treated as clean only when: (a) at least one
current HS2022 code names it as predecessor in Conversions, and (b) every
one of those (new, old) pairs is tagged 1:1 or n:1 in Correlations. Anything
else (no successor at all, or any 1:n/n:n tag on a Conversions-named pair)
is written with `hs6_code` blank and flagged UNRESOLVED, never guessed from
this table alone -- see EMPIRICAL_OVERRIDES below for the one case (854150)
where the table's own answer was checked against trade data and rejected.
This is computed generically from the two tabs, not hardcoded per code,
since the point of the bridge is to catch cases where an assumption (like
the "854140/854150 both split six ways" note in verification_round2.md)
turns out not to hold up against the real table.

Both tabs are read with openpyxl, not the hand-rolled zipfile/xml.etree
parser this module used originally. The original parser did track each
cell's r= reference and was not, on inspection, actually misaligning rows;
the real surprises were structural: the Conversions tab carries four always-
blank trailing columns (explaining the four Nones seen in its header row),
and the Correlations tab has two header rows -- a merged "Between" title
over columns A:B, then the real "HS2022"/"HS2017"/"Relationship" header
below it -- not one. openpyxl exposes both directly (iter_rows,
ws.merged_cells.ranges) instead of requiring that structure to be inferred
from raw XML.

EMPIRICAL_OVERRIDES exists because the correlation table can name a
predecessor/successor that trade data flatly contradicts. Checked directly
against the workbook: HS2022 854151 and 854159 each name HS2017 851712
(cellular telephones) as their sole Conversions predecessor -- not 854150,
and not because of a missed continuation row (the Conversions tab has zero
merged cells, zero blank-predecessor continuation rows, and zero codes
listed twice; it is structurally one predecessor per current code, and for
854151/854159 it names the wrong one). Census import value settles it
instead: 854150 (H5) runs $400-826M/yr from 2018-2021 then goes to exactly
zero from 2022; 854151+854159 (H6) are exactly zero through 2021 then pick
up at $819.9M in 2022, a 0.7% gap from 854150's final year. 854151 is new
in HS2022 for "semiconductor-based transducers" (added to the 8541 heading
text that revision); 854159 keeps 854150's old "other semiconductor
devices" title verbatim. That is a real split with no plausible mechanism
running through mobile telephones.

Usage: .venv/bin/python -m ingest.hs_bridge
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import openpyxl
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"

CORRELATION_URL = (
    "https://unstats.un.org/unsd/classifications/Econ/tables/"
    "HS2022toHS2017ConversionAndCorrelationTables.xlsx"
)
CORRELATION_CACHE_NAME = "un_hs2022_to_hs2017_correlation.xlsx"

CONVERSIONS_SHEET = "HS2022-HS2017 Conversions"
CORRELATIONS_SHEET = "HS2022-HS2017 Correlations"
CLEAN_RELATIONSHIPS = {"1:1", "n:1"}

VINTAGE_BREAK_YEAR = 2022

# The 22 candidate HS6 codes verified live against the HS2017 (H5) code list
# in analysis/verification_round1_findings.md section 1.
CODES_BY_BASKET = {
    "semiconductors_and_sme": [
        "854110", "854121", "854129", "854130", "854140", "854150", "854160", "854190",
        "854231", "854232", "854233", "854239", "854290",
        "848610", "848620", "848630", "848640", "848690",
    ],
    "rare_earths_and_magnets": [
        "280530", "284610", "284690", "850511",
    ],
}
BASKET_BY_CODE = {
    code: basket for basket, codes in CODES_BY_BASKET.items() for code in codes
}

# Codes where the WCO correlation table's own answer is checked against
# Census import value and rejected, rather than taken as given. Currently
# just 854150: the table names HS2017 851712 (cellular telephones) as sole
# Conversions predecessor for both HS2022 854151 and 854159, which has no
# plausible mechanism and no trade-value support. Verified empirically instead (see
# analysis notes and the module docstring): 854150 (H5) is $400-826M/yr
# 2018-2021 then exactly zero from 2022; 854151+854159 (H6) are exactly
# zero through 2021 then $819.9M in 2022, a 0.7% gap from 854150's final
# year. This is a hardcoded, one-off override, not a generic algorithm --
# each entry here must carry its own verified evidence in EMPIRICAL_NOTE.
EMPIRICAL_OVERRIDES: dict[str, list[str]] = {
    "854150": ["854151", "854159"],
}
EMPIRICAL_NOTE = {
    "854150": (
        "Resolved empirically via US Census import-value continuity across the "
        "2021/2022 classification break, not via the WCO correlation table: "
        "854150 (H5) = $825,916,060 in 2021; 854151 + 854159 (H6) = $819,940,556 "
        "in 2022 (-0.7%). The WCO HS2022-to-HS2017 correlation table names "
        "851712 (cellular telephones) as the Conversions-tab predecessor for "
        "both 854151 and 854159; that attribution is not corroborated by trade "
        "value and is not used here."
    ),
}
# Per-successor-code asides layered onto the row for that specific hs6_code,
# independent of which H5 code it resolved from. Observational only -- not
# investigated further here.
PER_SUCCESSOR_NOTE = {
    "854151": (
        "854151 US import value: $24,800,504 (2022), $21,096,047 (2023), "
        "$17,958,080 (2024), then $178,763,927 (2025), roughly an 8-9x jump "
        "in the final year. Possible series break, flagged for later "
        "investigation, not investigated here."
    ),
}


def fetch_correlation_workbook() -> bytes:
    """GET the UN Stats HS2022-to-HS2017 correlation workbook, caching the
    raw bytes under data/raw/ and reading from cache on rerun."""
    cache_file = CACHE_DIR / CORRELATION_CACHE_NAME
    if cache_file.exists():
        return cache_file.read_bytes()

    resp = requests.get(CORRELATION_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(resp.content)
    return resp.content


def load_primary_successors(workbook_bytes: bytes) -> dict[str, list[str]]:
    """Invert the "HS2022-HS2017 Conversions" tab: hs2017_code -> every
    current hs2022_code that names it as predecessor. Exactly one row per
    hs2022_code in that tab (verified: 5,613 rows, 5,613 distinct hs2022
    codes, zero merged cells, zero blank-predecessor continuation rows), so
    this is the WCO's own candidate-successor list, not derived. One header
    row (columns C-F always blank in this tab -- formatting only, verified
    against all 5,613 data rows)."""
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    ws = wb[CONVERSIONS_SHEET]

    successors: dict[str, list[str]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        hs2022, hs2017 = row[0], row[1]
        if hs2022 is None or hs2017 is None:
            continue
        successors.setdefault(str(hs2017).strip(), []).append(str(hs2022).strip())
    return successors


def load_relationship_by_pair(workbook_bytes: bytes) -> dict[tuple[str, str], str]:
    """Every (hs2022_code, hs2017_code) -> relationship tag (1:1/n:1/1:n/n:n)
    from the "HS2022-HS2017 Correlations" tab, used to check the pairs
    Conversions names as candidates, not to enumerate candidates itself.
    Two header rows here, not one: a merged "Between" title over columns
    A:B (row 1), then the real "HS2022"/"HS2017"/"Relationship" header
    (row 2); data starts row 3."""
    wb = openpyxl.load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    ws = wb[CORRELATIONS_SHEET]

    relationship_by_pair = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        hs2022, hs2017, relationship = row[0], row[1], row[2]
        if hs2022 is None or hs2017 is None or relationship is None:
            continue
        relationship_by_pair[(str(hs2022).strip(), str(hs2017).strip())] = str(relationship).strip()
    return relationship_by_pair


def resolve_successors(
    hs2017_code: str,
    primary_successors: dict[str, list[str]],
    relationship_by_pair: dict[tuple[str, str], str],
) -> dict:
    """For one HS2017 (H5) code, find its HS2022 (H6) successor(s).

    Candidates come only from the Conversions tab (the WCO's own named
    predecessor per current code), never invented.

    Two cases:
    - The code survives under its own number (a Conversions candidate equal
      to itself, tagged 1:1/n:1 in Correlations): that self-mapping is the
      continuation, taken as clean regardless of what else the Conversions
      tab also names as its (possibly unrelated, possibly messy) other
      candidates. This matters in practice: 8549 ("electrical and electronic
      waste and scrap", new in HS2022) is a from-scratch heading with no
      real ancestor, and the Conversions tab's single-predecessor-per-new-
      code algorithm sometimes names a completely unrelated old code (e.g.
      854231) as its nearest match for one of these new subheadings, tagged
      n:n in Correlations. That ambiguity is about the NEW code's forced,
      meaningless "predecessor" pick, not about whether 854231 itself still
      means what it meant in HS2017, so it is recorded as an aside rather
      than blanking the clean self-mapping.
    - The code does not survive under its own number (no self-candidate):
      every one of its Conversions candidates must be clean (1:1/n:1) to
      accept the split (e.g. 854140 -> 854141/142/143/149). Any messy
      candidate, or no candidate at all, comes back unresolved.
    """
    candidates = sorted(set(primary_successors.get(hs2017_code, [])))
    self_relationship = relationship_by_pair.get((hs2017_code, hs2017_code))

    if hs2017_code in candidates and self_relationship in CLEAN_RELATIONSHIPS:
        extra = [c for c in candidates if c != hs2017_code]
        ambiguous_extra = [c for c in extra if relationship_by_pair.get((c, hs2017_code)) not in CLEAN_RELATIONSHIPS]
        clean_extra = [c for c in extra if relationship_by_pair.get((c, hs2017_code)) in CLEAN_RELATIONSHIPS]
        return {
            "clean": True,
            "successors": [hs2017_code] + clean_extra,
            "relationships": sorted({self_relationship, *(relationship_by_pair.get((c, hs2017_code)) for c in clean_extra)}),
            "ambiguous_extra": ambiguous_extra,
            "reason": None,
        }

    if not candidates:
        return {
            "clean": False,
            "successors": [],
            "relationships": [],
            "ambiguous_extra": [],
            "reason": "no current HS2022 code names this as its predecessor in the Conversions tab",
        }

    relationships = [relationship_by_pair.get((c, hs2017_code)) for c in candidates]
    if any(rel not in CLEAN_RELATIONSHIPS for rel in relationships):
        bad = {c: rel for c, rel in zip(candidates, relationships) if rel not in CLEAN_RELATIONSHIPS}
        return {
            "clean": False,
            "successors": candidates,
            "relationships": sorted(set(r for r in relationships if r)),
            "ambiguous_extra": [],
            "reason": f"code does not survive under its own number, and not every Conversions-named "
            f"successor is a clean 1:1/n:1 split: {bad}",
        }

    return {
        "clean": True,
        "successors": candidates,
        "relationships": sorted(set(relationships)),
        "ambiguous_extra": [],
        "reason": None,
    }


def build_bridge_rows(
    primary_successors: dict[str, list[str]],
    relationship_by_pair: dict[tuple[str, str], str],
) -> tuple[list[dict], list[dict]]:
    """Returns (rows, unresolved_rows). Every row has the same schema.

    code_status distinguishes a structural non-event (a code retiring or not
    yet existing in a given vintage) from an actual data gap: 'active' for a
    code that carries the same number across the whole 2018-2025 span,
    'retired_2021' for an H5 row whose number stops being used after 2021,
    'introduced_2022' for an H6 row whose number did not exist before 2022.
    A mart built on canonical_product_id must not render a retired/not-yet-
    introduced code's missing years as a data quality problem.
    """
    rows: list[dict] = []
    unresolved: list[dict] = []

    for basket, codes in CODES_BY_BASKET.items():
        for h5_code in codes:
            if h5_code in EMPIRICAL_OVERRIDES:
                successors = EMPIRICAL_OVERRIDES[h5_code]
                is_unchanged = False
                note_h5 = "Native HS2017 (H5) code."
                base_note = EMPIRICAL_NOTE[h5_code]
                per_successor_note = {c: (" " + PER_SUCCESSOR_NOTE[c]) if c in PER_SUCCESSOR_NOTE else "" for c in successors}
                h6_notes = {c: base_note + per_successor_note[c] for c in successors}
            else:
                resolution = resolve_successors(h5_code, primary_successors, relationship_by_pair)
                rel_str = "/".join(resolution["relationships"]) if resolution["relationships"] else "none"

                if not resolution["clean"]:
                    rows.append(
                        {
                            "canonical_product_id": h5_code,
                            "hs_version": "H5",
                            "hs6_code": h5_code,
                            "code_status": "retired_2021",
                            "basket": basket,
                            "notes": "Native HS2017 (H5) code.",
                            "vintage_break_year": "",
                        }
                    )
                    row = {
                        "canonical_product_id": h5_code,
                        "hs_version": "H6",
                        "hs6_code": "",
                        "code_status": "",
                        "basket": basket,
                        "notes": (
                            "UNRESOLVED, manual review required. UN Stats HS2022-to-HS2017 "
                            f"correlation table gives no unambiguous HS2022 successor "
                            f"({resolution['reason']}; relationship tag(s) found: {rel_str})."
                        ),
                        "vintage_break_year": str(VINTAGE_BREAK_YEAR),
                    }
                    rows.append(row)
                    unresolved.append(row)
                    continue

                successors = resolution["successors"]
                is_unchanged = successors == [h5_code]
                aside = ""
                if resolution["ambiguous_extra"]:
                    aside = (
                        f" Also named by the Conversions tab as a partial (n:n, not attributed here) "
                        f"predecessor of {', '.join(resolution['ambiguous_extra'])}; not a clean split, "
                        "so no value is routed there."
                    )
                note_h5 = "Native HS2017 (H5) code."
                h6_notes = {
                    h6_code: (
                        f"UN Stats HS2022-to-HS2017 correlation table: relationship {rel_str}"
                        + (
                            ""
                            if is_unchanged
                            else f" ({len(successors)}-way split of {h5_code}: {', '.join(successors)})."
                        )
                        + aside
                    )
                    for h6_code in successors
                }

            h5_status = "active" if is_unchanged else "retired_2021"
            rows.append(
                {
                    "canonical_product_id": h5_code,
                    "hs_version": "H5",
                    "hs6_code": h5_code,
                    "code_status": h5_status,
                    "basket": basket,
                    "notes": note_h5,
                    "vintage_break_year": "",
                }
            )
            for h6_code in successors:
                h6_status = "active" if is_unchanged else "introduced_2022"
                rows.append(
                    {
                        "canonical_product_id": h5_code,
                        "hs_version": "H6",
                        "hs6_code": h6_code,
                        "code_status": h6_status,
                        "basket": basket,
                        "notes": h6_notes[h6_code],
                        "vintage_break_year": "" if is_unchanged else str(VINTAGE_BREAK_YEAR),
                    }
                )

    return rows, unresolved


def write_bridge(rows: list[dict]) -> Path:
    path = REFERENCE_DIR / "hs_bridge.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "canonical_product_id", "hs_version", "hs6_code", "code_status",
        "basket", "notes", "vintage_break_year",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    print("Fetching UN Stats HS2022-to-HS2017 correlation table...")
    workbook_bytes = fetch_correlation_workbook()

    print("Parsing Conversions and Correlations tabs...")
    primary_successors = load_primary_successors(workbook_bytes)
    relationship_by_pair = load_relationship_by_pair(workbook_bytes)
    print(
        f"  {len(primary_successors)} HS2017 codes with a named HS2022 successor; "
        f"{len(relationship_by_pair)} correlation pairs"
    )

    print(f"Resolving {sum(len(v) for v in CODES_BY_BASKET.values())} candidate H5 codes...")
    rows, unresolved = build_bridge_rows(primary_successors, relationship_by_pair)

    path = write_bridge(rows)
    print(f"Wrote {path.relative_to(REPO_ROOT)}: {len(rows)} rows")

    if unresolved:
        print(f"\n{len(unresolved)} UNRESOLVED row(s), manual review required:")
        for row in unresolved:
            print(f"  - canonical_product_id={row['canonical_product_id']} ({row['basket']}): {row['notes']}")
    else:
        print("\nNo unresolved rows.")


if __name__ == "__main__":
    main()
