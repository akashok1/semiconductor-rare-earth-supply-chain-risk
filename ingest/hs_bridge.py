"""HS classification bridge: canonical products across the HS2017/HS2022 split.

US import data is native H5 (HS2017) through 2021 and H6 (HS2022) from 2022
onward. A canonical product must map to every HS6 code that ever represented
it, across classification vintages, so marts can group by
`canonical_product_id` instead of raw HS code. This module builds that
bridge for every H5 code marked `include` in
`data/reference/manual/basket_codes.csv`.

Source of truth for the HS2017-to-HS2022 correlation itself is the UN Stats
correlation table (unstats.un.org/unsd/classifications/Econ), not guesswork:
the workbook at `config.UN_HS_CORRELATION_URL`, cached under `data/raw/`.
That workbook ships two tabs, read together:

- "HS2022-HS2017 Conversions": exactly one row per current HS2022 code,
  naming the single HS2017 code the WCO treats as its predecessor. A code
  retired in HS2022 with nothing claiming it as predecessor here simply
  never appears in this tab. This is the candidate-successor list.
- "HS2022-HS2017 Correlations": every HS2022/HS2017 code pair that overlaps
  at all (thousands more rows than Conversions), each tagged with a
  relationship type (1:1, n:1, 1:n, n:n). Used here only to look up the
  relationship tag for the specific (new, old) pairs Conversions already
  named as candidates.

A code's forward mapping is treated as clean only when: (a) at least one
current HS2022 code names it as predecessor in Conversions, and (b) every
one of those (new, old) pairs is tagged 1:1 or n:1 in Correlations. Anything
else (no successor at all, or any 1:n/n:n tag on a Conversions-named pair)
is written with `hs6_code` blank and flagged UNRESOLVED, never guessed from
this table alone.

`data/reference/manual/bridge_overrides.csv` holds the cases where the
table's own answer is checked against trade data and rejected instead of
taken as given -- see that file for the basis and evidence per override.

Usage: .venv/bin/python -m ingest.hs_bridge
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.config import UN_HS_CORRELATION_URL  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
BASKET_CODES_PATH = REFERENCE_DIR / "manual" / "basket_codes.csv"
BRIDGE_OVERRIDES_PATH = REFERENCE_DIR / "manual" / "bridge_overrides.csv"
OUTPUT_PATH = REFERENCE_DIR / "generated" / "hs_bridge.csv"

CORRELATION_CACHE_NAME = "un_hs2022_to_hs2017_correlation.xlsx"

CONVERSIONS_SHEET = "HS2022-HS2017 Conversions"
CORRELATIONS_SHEET = "HS2022-HS2017 Correlations"
CLEAN_RELATIONSHIPS = {"1:1", "n:1"}

VINTAGE_BREAK_YEAR = 2022


class HsBridgeConfigError(RuntimeError):
    """Raised when the manual reference CSVs are inconsistent with each
    other (a duplicate code, or an override naming a code that isn't an
    included basket code)."""


class HsBridgeVintageError(RuntimeError):
    """Raised when the generated hs_bridge.csv does not define an unambiguous
    vintage split: exactly one distinct non-null vintage_break_year and
    exactly two hs_versions."""


def fetch_correlation_workbook() -> bytes:
    """GET the UN Stats HS2022-to-HS2017 correlation workbook, caching the
    raw bytes under data/raw/ and reading from cache on rerun."""
    cache_file = CACHE_DIR / CORRELATION_CACHE_NAME
    if cache_file.exists():
        return cache_file.read_bytes()

    resp = requests.get(UN_HS_CORRELATION_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(resp.content)
    return resp.content


def load_basket_codes() -> dict[str, list[str]]:
    """Read basket_codes.csv, returning {basket: [h5_code, ...]} for rows
    with decision == include, in file order. Fails loudly on a duplicate
    hs6_code: the file is one row per H5 code, include or exclude alike."""
    seen: set[str] = set()
    codes_by_basket: dict[str, list[str]] = {}
    with BASKET_CODES_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            code = row["hs6_code"]
            if code in seen:
                raise HsBridgeConfigError(
                    f"duplicate hs6_code {code!r} in {BASKET_CODES_PATH.relative_to(REPO_ROOT)}"
                )
            seen.add(code)
            if row["decision"] == "include":
                codes_by_basket.setdefault(row["basket"], []).append(code)
    return codes_by_basket


def load_bridge_overrides(included_codes: set[str]) -> dict[str, list[str]]:
    """Read bridge_overrides.csv, returning {h5_code: [h6_code, ...]}. Fails
    loudly if an override names an h5_code that basket_codes.csv does not
    mark include."""
    overrides: dict[str, list[str]] = {}
    with BRIDGE_OVERRIDES_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            h5_code = row["h5_code"]
            if h5_code not in included_codes:
                raise HsBridgeConfigError(
                    f"{BRIDGE_OVERRIDES_PATH.relative_to(REPO_ROOT)} references h5_code "
                    f"{h5_code!r}, which is not an included code in "
                    f"{BASKET_CODES_PATH.relative_to(REPO_ROOT)}"
                )
            overrides.setdefault(h5_code, []).append(row["h6_code"])
    return overrides


def load_primary_successors(workbook_bytes: bytes) -> dict[str, list[str]]:
    """Invert the "HS2022-HS2017 Conversions" tab: hs2017_code -> every
    current hs2022_code that names it as predecessor. Exactly one row per
    hs2022_code in that tab, so this is the WCO's own candidate-successor
    list, not derived. One header row."""
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
    Two header rows: a merged "Between" title over columns A:B (row 1), then
    the real "HS2022"/"HS2017"/"Relationship" header (row 2); data starts
    row 3."""
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
      tab also names as its other candidates. A new-in-HS2022 heading can be
      forced to name an unrelated old code as its nearest match, tagged n:n
      in Correlations; that ambiguity is about the NEW code's meaningless
      "predecessor" pick, not about whether the old code itself still means
      what it meant in HS2017.
    - The code does not survive under its own number (no self-candidate):
      every one of its Conversions candidates must be clean (1:1/n:1) to
      accept the split. Any messy candidate, or no candidate at all, comes
      back unresolved.
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
    codes_by_basket: dict[str, list[str]],
    overrides: dict[str, list[str]],
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

    for basket, codes in codes_by_basket.items():
        for h5_code in codes:
            if h5_code in overrides:
                successors = overrides[h5_code]
                is_unchanged = successors == [h5_code]
                note_h5 = "Native HS2017 (H5) code."
                h6_notes = {c: "override, see bridge_overrides.csv" for c in successors}
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
                note_h5 = "Native HS2017 (H5) code."
                h6_notes = {
                    h6_code: (
                        f"relationship {rel_str}"
                        if is_unchanged
                        else f"relationship {rel_str}, split of {h5_code} into {', '.join(successors)}"
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
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "canonical_product_id", "hs_version", "hs6_code", "code_status",
        "basket", "notes", "vintage_break_year",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_PATH


@dataclass(frozen=True)
class VintagePlan:
    """The vintage split hs_bridge.csv defines: years before break_year use
    old_version's codes, years from break_year onward new_version's."""

    break_year: int
    old_version: str
    new_version: str
    codes_by_version: dict[str, frozenset[str]]


def read_vintage_plan() -> VintagePlan:
    """Read the generated hs_bridge.csv and return its vintage split. Raises
    HsBridgeVintageError unless the bridge has exactly one distinct non-null
    vintage_break_year and exactly two hs_versions."""
    with OUTPUT_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))

    breaks = {r["vintage_break_year"] for r in rows if r["vintage_break_year"].strip()}
    if len(breaks) != 1:
        raise HsBridgeVintageError(
            f"hs_bridge.csv has {len(breaks)} distinct non-null "
            f"vintage_break_year value(s) {sorted(breaks)}, expected exactly one."
        )

    codes_by_version: dict[str, set[str]] = {}
    for r in rows:
        codes_by_version.setdefault(r["hs_version"], set()).add(r["hs6_code"])
    if len(codes_by_version) != 2:
        raise HsBridgeVintageError(
            f"hs_bridge.csv has hs_version values {sorted(codes_by_version)}, "
            "expected exactly two (one each side of the vintage break)."
        )
    old_version, new_version = sorted(codes_by_version)

    return VintagePlan(
        break_year=int(breaks.pop()),
        old_version=old_version,
        new_version=new_version,
        codes_by_version={v: frozenset(c) for v, c in codes_by_version.items()},
    )


def main() -> None:
    print("Loading basket_codes.csv and bridge_overrides.csv...")
    codes_by_basket = load_basket_codes()
    included_codes = {code for codes in codes_by_basket.values() for code in codes}
    overrides = load_bridge_overrides(included_codes)
    print(f"  {len(included_codes)} included H5 code(s) across {len(codes_by_basket)} basket(s)")

    print("Fetching UN Stats HS2022-to-HS2017 correlation table...")
    workbook_bytes = fetch_correlation_workbook()

    print("Parsing Conversions and Correlations tabs...")
    primary_successors = load_primary_successors(workbook_bytes)
    relationship_by_pair = load_relationship_by_pair(workbook_bytes)
    print(
        f"  {len(primary_successors)} HS2017 codes with a named HS2022 successor; "
        f"{len(relationship_by_pair)} correlation pairs"
    )

    print(f"Resolving {len(included_codes)} candidate H5 codes...")
    rows, unresolved = build_bridge_rows(codes_by_basket, overrides, primary_successors, relationship_by_pair)

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
