# Traceability matrix: Semiconductor and Rare Earth Supply Chain Risk

Every business requirement in [`02_brd.md`](02_brd.md) (v1.2), traced to
the model that satisfies it, the dbt test that evidences it, and the
dashboard element that shows it.

There is no FRD (03) and no standalone UAT plan (06). The dbt tests
column stands in for UAT evidence: `make dbt-test` runs 97 tests (13
custom in `dbt/tests/`, 84 schema tests), all passing on 2026-09-26.
Where no test exists, the evidence column names what does.

The dashboard is built by hand in Tableau Public from `exports/*.csv`
(see [`07_assumptions_limitations.md`](07_assumptions_limitations.md)
§2.1). Its four sheets are named below as **2x2**, **Top suppliers**,
**HHI trend** and **Chokepoints**; its controls are the Product, Year,
Coast, HHI line and Exposure line parameters.

Status:

- **Met**: built and evidenced.
- **Partial**: built, with a gap named in Notes.
- **Not built**: disclosed in the README and the banners on the baselined
  docs.
- **Pending**: depends on the hand-built dashboard being published. "Met in workbook, published pending" means the element exists in the Tableau workbook but has no public URL yet.

Schema-test shorthand: `unique(...)` is the generic
`unique_combination_of_columns` test on the listed grain; `not_null` and
`accepted_values` are dbt built-ins declared in `schema.yml`.

## 8.1 Supplier concentration

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-01 | HHI per product per year | `fct_concentration.hhi` | `assert_hhi_between_0_and_10000`; `assert_supplier_shares_sum_to_one`; `unique(canonical_product_id, year)` | 2x2 x-axis; HHI trend | Met | 22 products x 8 years = 176 rows, no gaps. A manual reconciliation for one sampled product-year is not recorded as a test |
| BR-02 | Top share, top 3 share, supplier count beside HHI | `fct_concentration.top1_share`, `top3_share`, `supplier_count`, `effective_suppliers` | `assert_supplier_shares_sum_to_one`; `not_null` on `fct_supplier_share.rank` | Top suppliers; 2x2 tooltip (`top1_partner_name`, `top1_share`, `effective_suppliers`) | Met | Why both families are shown: [`04_data_dictionary.md`](04_data_dictionary.md) |
| BR-03 | Named top supplier country | `fct_concentration.top1_partner_name`, `top1_partner_iso3` | `assert_comtrade_partners_matched`; `not_null` on `partner_name`, `partner_iso3` | Top suppliers; 2x2 tooltip | Met | Partner 490 overridden to Taiwan in `manual/comtrade_partner_overrides.csv` |
| BR-04 | Classify against a cited published threshold | None: the line is a Tableau parameter, marts carry no threshold column | None | HHI line parameter, default 4,000 | Met | Guideline changed from DOJ/FTC merger bands to European Commission (2021) HHI 0.4, a single line rather than bands. Cited in `docs/04`, `docs/07` §2.1 and the README |
| BR-05 | Group by canonical product | `fct_supplier_share`, `fct_concentration` on `canonical_product_id`; `hs_bridge` seed | `assert_h6_boundary_year_matches_bridge`; `unique(canonical_product_id, year, partner_code)` | Product parameter; Tableau CASE mapping HS2022 successors to 854140/854150 | Met | Exposure marts group on HS6 by design, per BR-34 |
| BR-06 | Raw rare earths and magnets reported separately | 280530 and 850511 are separate canonical products in `fct_concentration` | `unique(canonical_product_id, year)` | Product parameter; HHI trend | Met | Hypothesis disproven: 280530 (HHI 9,749 in 2023) is more concentrated than 850511 (6,413). Value-base caveat (about $8M in 2025) in README and `docs/07` §3.3 |

## 8.2 Chokepoint exposure

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-07 | Exposure per code x chokepoint, zeros published | `fct_exposure` | `unique(hs6_code, year, chokepoint_id, threshold_km, weighting, dest_coast)`; `not_null` on `exposure`; `assert_exposure_within_vessel_coverage`; `assert_national_exposure_within_coast_coverage` | Chokepoints | Met | 172,032 rows = every code-year x 28 chokepoints x 4 thresholds x 2 weightings x 4 coasts, zeros included. The dashboard shows 200km rows of 1% or more |
| BR-08 | Computed routing, committed as inspectable data | `ingest/routing.py` -> `generated/routes.csv`, `generated/routing_matrix.csv`; `stg_routes`, `stg_routing_matrix`, `int_route_crossings`, `int_port_weights`, `int_country_crossing_share` | `assert_weighted_ports_routed_to_every_coast`; `assert_port_weights_sum_to_one`; `assert_crossing_share_between_0_and_1`; `assert_chokepoint_risk_set_matched` | None (reference data) | Met | Matrix is 1,253 ports x 3 coasts x 28 chokepoints, distance only. Thresholds are applied in dbt (`crossing_thresholds_km`), not stored in the file |
| BR-09 | Exposure stated as modelled, naming what it ignores | Labelling only | None | 2x2 y-axis label: "Largest exposure to one risky chokepoint (modelled)" | Met in workbook, published pending | Also stated in README "What this cannot support", `docs/07` §2 and §3.1. "One representative port per country" is retired: every container port is weighted |
| BR-10 | Exposure ranking at 50, 100, 200, 300km | `fct_exposure.threshold_km`; `fct_exposure_summary.risk_exposure_100`, `risk_exposure_300` | `not_null` on the band columns | Quadrant calc: "Distance sensitive" | Met | Reframed as quadrant change at the exposure line between 100 and 300km (`docs/07` §3.2): none in 2025; 10 west-coast Taiwan Strait points 2018-2024. A full rank-order comparison is not published |
| BR-11 | View exposure for a single chokepoint | `fct_exposure` | As BR-07 | Chokepoints (top 10 at 200km, 1% or more) | Partial | No chokepoint filter over all 28. Chokepoints under 1% are in the mart and CSV, not on the dashboard |

## 8.3 Trend and event history

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-12 | Continuous 2018-2025 series across the vintage break | `fct_concentration` | `unique(canonical_product_id, year)` | HHI trend | Met | Every product has all 8 years; 854140 and 854150 run unbroken across 2021/2022 |
| BR-13 | Flag years affected by classification change, continuity test | `hs_version` carried in `fct_exposure`, `fct_exposure_summary` | `assert_h6_boundary_year_matches_bridge` (boundary year only) | None | Partial | No comparability flag column or dashboard annotation. The value-continuity test is not built; the check was run by query (`docs/07` §6.2) |
| BR-14 | One event study | None | None | None | Not built | D-7. PortWatch transits and the RED SEA TENSIONS disruption rollup are loaded and staged for it |
| BR-15 | Extend series to earlier vintages | None | None | None | Not built | Could-have |

## 8.4 Data trust and quality

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-16 | Exclude PortWatch blackout dates | None: no mart reads transits | None | None | Not built | Deferred with the event study |
| BR-17 | Flag signal interference and transponder suppression | None | None | None | Not built | Hormuz is in the risk set with GPS jamming as part of its reason; no flag column |
| BR-18 | Flag sensor coverage breaks | None | None | None | Not built | |
| BR-19 | Pin data version across boundary revisions | None | None | None | Not built | Raw tables carry `source_file` and `ingested_at` but no pinned version |
| BR-20 | Fail loudly on refused access | `ingest/*.py` | None (ingest code, not dbt) | None | Met | Every ingest script raises on auth failure or non-200 and never writes a partial file. Evidence is the code, not a test |
| BR-21 | Lineage and data dictionary | All models; `dbt docs generate` | None | None | Met | [`04_data_dictionary.md`](04_data_dictionary.md) covers every column of the four exported marts |

## 8.5 Delivery and usability

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-22 | Public dashboard, no login | `exports/*.csv` via `ingest/export.py` | None | Tableau Public workbook | Pending | Built by hand; link is a placeholder in the README |
| BR-23 | Excel scenario workbook | None | None | None | Not built | D-10 |
| BR-24 | Single landing view answering the decision, vessel coverage beside exposure, codes not blended | `fct_exposure_summary` | `unique(hs6_code, year, weighting, dest_coast)`; `assert_exposure_summary_covers_coast_shares`; `not_null` on `risk_max_exposure_200`, `risk_max_chokepoint` | 2x2 with quadrant labels: Buffer stock + second supplier, Qualify second supplier, Hold buffer stock, Monitor, Distance sensitive | Met | One point per HS6 code; `vessel_coverage` is on every row for the tooltip |
| BR-25 | Interactive tool to vary the proximity threshold | None | None | None | Not built | Could-have. The 100-300km band stands in for it |

## 8.6 Operation and reproducibility

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-26 | Reproducible from a clean clone | `Makefile` (`make all`, `make export`) | Full `dbt build` | None | Partial | Runbook in README. Not yet verified once against a fresh clone |
| BR-27 | Scheduled refresh | None | None | None | Not built | Manual refresh by decision: Comtrade and Census are annual, and so is the decision. No GitHub Actions |
| BR-28 | No credentials in version control | `ingest/config.py` reads secrets from the environment | None | None | Met | `.env` is gitignored. History not re-audited with a secret scanner for this matrix |
| BR-29 | Respect fair usage | `ingest/*.py` cache-first | None | None | Met | Every response cached under `data/raw/`; a rerun costs zero calls |
| BR-30 | Extend to new products without logic changes | `manual/basket_codes.csv` -> `hs_bridge` -> all models | `assert_h6_boundary_year_matches_bridge` | Product parameter | Partial | No transformation change is needed. The Tableau product-name CASE and successor CASE would need a new branch |

## 8.7 Measurement integrity

| BR | Requirement (short) | Model | dbt tests (UAT evidence) | Dashboard element | Status | Notes |
|---|---|---|---|---|---|---|
| BR-31 | Vessel share beside every exposure figure | `fct_exposure_summary.vessel_coverage`; `fct_exposure.vessel_coverage` | `not_null` on `vessel_coverage`; `assert_exposure_within_vessel_coverage`; `assert_coast_total_ves_val_matches_porths` | 2x2 tooltip | Met | Exported once per code-year in the summary; omitted from the `fct_exposure` CSV to avoid repeating it on every row |
| BR-32 | Validate every concordance against value continuity | `manual/bridge_overrides.csv` (854150 override with evidence) -> `hs_bridge` | `assert_h6_boundary_year_matches_bridge` | None | Partial | Continuity checked for all 22 H5 codes by query (`docs/07` §6.1-6.2). The continuity test is not part of the build |
| BR-33 | Distinguish structural absence from missing data | `hs_bridge.code_status` (active, retired_2021, introduced_2022) | None | None | Partial | `code_status` is in the bridge but not carried into any mart. The dashboard shows a code only in years it exists |
| BR-34 | Exposure at HS6 grain, coverage never blended | `fct_exposure`, `fct_exposure_summary` keyed on `hs6_code` | `unique(hs6_code, ...)` on both marts | 2x2 (one point per HS6 code) | Met | 854140's successors range 2.75% to 95.2% containerized vessel |

## Summary

| Status | Count | BRs |
|---|---|---|
| Met | 17 | 01, 02, 03, 04, 05, 06, 07, 08, 10, 12, 20, 21, 24, 28, 29, 31, 34 |
| Partial | 6 | 11, 13, 26, 30, 32, 33 |
| Pending | 2 | 09 (met in workbook, published pending), 22 (public URL) |
| Not built | 9 | 14, 15, 16, 17, 18, 19, 23, 25, 27 |
