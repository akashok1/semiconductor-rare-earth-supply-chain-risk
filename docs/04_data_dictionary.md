# Data dictionary: Semiconductor and Rare Earth Supply Chain Risk

The four marts Tableau reads, as written to `exports/*.csv` by `make
export` (`ingest/export.py`). Column descriptions come from
`dbt/models/marts/schema.yml`; the "Plain English" column says what a
committee member should read into each one. Types are the Postgres types
in `analytics.*`.

Conventions:

- **Measured** figures come straight from a source (Comtrade, Census).
  **Modelled** figures depend on computed routes and port weights. Every
  exposure column is modelled.
- Ratios are fractions (0.25 = 25%), rounded to 6 decimals in the export
  only. The models keep full precision.
- Dollar values are nominal US dollars, not inflation adjusted.
- Years run 2018 to 2025. HS2017 (`H5`) codes cover 2018 to 2021, HS2022
  (`H6`) codes 2022 on. A code missing in a year it did not exist is a
  structural absence, not missing data.
- No mart carries a threshold column. The HHI line (4,000) and exposure
  line (25%) are Tableau parameters.

| Mart | Grain | Rows | Kind | Dashboard use |
|---|---|---|---|---|
| `fct_exposure_summary` | HS6 code x year x weighting x dest_coast | 1,536 | Modelled y-axis, measured x-axis | 2x2 |
| `fct_supplier_share` | canonical product x year x partner | 8,350 | Measured | Top 10 suppliers |
| `fct_concentration` | canonical product x year | 176 | Measured | HHI trend |
| `fct_exposure` | HS6 code x year x chokepoint x threshold_km x weighting x dest_coast | 172,032 | Modelled | Chokepoint drilldown |

---

## fct_exposure_summary

One 2x2 point per HS6 code, year, weighting and destination coast. Two
y-axis candidates: `risk_` (the dashboard's y-axis, over the manual
chokepoint risk set) and `flow_` (over all 28 chokepoints, drilldown
only). Each carries the winning chokepoint's exposure at 100 and 300km as
a band. Tie-break: exposure descending, then chokepoint name; the name is
`none` if the top exposure is 0. The x-axis is the canonical product's
HHI from `fct_concentration`.

Unique on `hs6_code, year, weighting, dest_coast`.

| Column | Type | Definition | Plain English |
|---|---|---|---|
| `basket` | text | `semiconductors_and_sme` or `rare_earths_and_magnets` | Which of the two product groups |
| `canonical_product_id` | text | Canonical product from the HS bridge | The product's stable ID across HS revisions. The six HS2022 successors map to 854140 or 854150 |
| `hs6_code` | text | HS6 code | The point on the 2x2 |
| `hs_version` | text | `H5` (HS2017) or `H6` (HS2022) | Which classification the code belongs to |
| `year` | integer | Calendar year | |
| `weighting` | text | `export_share` (headline) or `vessel_count` (sensitivity) | How a supplier country's value is split across its ports. The dashboard fixes `export_share` |
| `dest_coast` | text | `west`, `east`, `gulf` or `national` | Where the goods land. A coast value assumes all sea imports land there; `national` blends the three by actual coast share |
| `flow_max_chokepoint` | text | Highest-exposure chokepoint at 200km, all 28 | The busiest chokepoint on the route, disrupted or not |
| `flow_max_exposure_200` | numeric | Its exposure at 200km | |
| `flow_exposure_100` | numeric | Same chokepoint, at 100km | Low end of the distance band |
| `flow_exposure_300` | numeric | Same chokepoint, at 300km | High end of the distance band |
| `risk_max_chokepoint` | text | Highest-exposure chokepoint at 200km, risk set only | The disrupted chokepoint this code depends on most. The 2x2 label |
| `risk_max_exposure_200` | numeric | Its exposure at 200km | **The 2x2 y-axis.** Share of the code's total import value that would sail within 200km of that chokepoint |
| `risk_exposure_100` | numeric | Same chokepoint, at 100km | If the 100km and 300km values straddle the exposure line, the point is Distance sensitive |
| `risk_exposure_300` | numeric | Same chokepoint, at 300km | |
| `gen_val_total` | numeric | Census general import value, all countries and modes (USD) | Total US imports of the code. The exposure denominator |
| `cnt_val_total` | numeric | Census containerized vessel value, all countries (USD) | The part that travels by container ship |
| `vessel_coverage` | numeric | `cnt_val_total / gen_val_total` | The most exposure could ever be. A chip code near 0 here flies; its low exposure is a finding, not a gap |
| `unrouted_share` | numeric | Share of `cnt_val_total` from countries with no port weights (no ISO3, or no own or gateway ports) | Container value the model could not route. Stays in the denominator |
| `coast_residual` | numeric | Vessel value share landing outside the three coasts; national rows only, 0 on single-coast rows | Value landing at Great Lakes or interior ports, not routed |
| `hhi` | numeric | Canonical product's HHI for the year, 0 to 10,000 | **The 2x2 x-axis.** Measured supplier concentration. Same for every coast |
| `effective_suppliers` | numeric | `10,000 / hhi` | "Equivalent to this many equal-sized suppliers". In the tooltip |
| `top1_partner_name` | text | Largest partner for the canonical product-year | Top supplier country (family level for HS2022 successors) |
| `top1_share` | numeric | That partner's share of import value | |

## fct_supplier_share

Comtrade US import value and share per canonical product, year and
partner (measured). Partner values are summed across the product's HS6
codes before shares are taken. Partner ISO3 and name come from Comtrade's
partner list, manual overrides first (490 = Taiwan). "nes" and area
partners are kept and flagged.

Unique on `canonical_product_id, year, partner_code` and on
`canonical_product_id, year, rank`.

| Column | Type | Definition | Plain English |
|---|---|---|---|
| `basket` | text | Basket | |
| `canonical_product_id` | text | Canonical product | |
| `year` | integer | Calendar year | |
| `partner_code` | integer | UN M49 partner code. World (0) never appears | |
| `partner_iso3` | text | ISO3, or Comtrade's pseudo-code for aggregates. Override wins | |
| `partner_name` | text | Partner name | Supplier country. Country of origin, not of mining or fabrication |
| `is_aggregate_partner` | boolean | Comtrade group flag, or "nes" as a whole word in the name; false wherever a manual override exists | True for "not elsewhere specified" buckets, which are not real single suppliers. No partner in the current data is flagged |
| `import_value_usd` | numeric | US import value from that partner (USD) | |
| `share` | numeric | `import_value_usd / product-year total` | Supplier's share of US imports. Shares sum to 1 per product-year |
| `rank` | bigint | 1 = largest value; ties broken by `partner_code` | The dashboard shows ranks 1 to 10 |

## fct_concentration

Supplier concentration per canonical product and year, from
`fct_supplier_share` (measured). No threshold column.

Unique on `canonical_product_id, year`.

| Column | Type | Definition | Plain English |
|---|---|---|---|
| `basket` | text | Basket | |
| `canonical_product_id` | text | Canonical product | |
| `year` | integer | Calendar year | |
| `total_import_value_usd` | numeric | Sum of partner import value (USD) | Size of the dependency. 280530 is about $8M in 2025, 854140 about $10.9B |
| `hhi` | numeric | 10,000 x sum of squared partner shares | 0 = perfectly spread, 10,000 = one supplier. 4,000 is the European Commission (2021) concentration criterion |
| `effective_suppliers` | numeric | `10,000 / hhi` | |
| `top1_partner_name` | text | Largest partner | |
| `top1_partner_iso3` | text | Its ISO3 | |
| `top1_share` | numeric | Largest partner's share | Procurement reads this faster than HHI |
| `top3_share` | numeric | Share of the three largest partners (fewer if fewer exist) | |
| `supplier_count` | bigint | Partners with import value > 0 | Includes tiny suppliers; read with HHI |
| `n_codes` | bigint | HS6 codes with nonzero Comtrade value in the product-year | 1 for most products; 4 for 854140 and 2 for 854150 from 2022 |

## fct_exposure

Modelled chokepoint exposure per HS6 code, year, chokepoint, threshold,
weighting and destination coast (Census containerized value x computed
routes). `exposure = sum over countries of cnt_val x crossing_share /
gen_val_total`; national blends west, east and gulf by coast share.
Countries with no route stay in the denominator.

**Never sum across chokepoints.** One route crosses several (Panama and a
Caribbean passage), so a sum double counts and can exceed 100%.

Unique on `hs6_code, year, chokepoint_id, threshold_km, weighting,
dest_coast`. The export omits the per code-year diagnostic columns
(`gen_val_total`, `cnt_val_total`, `vessel_coverage`, `unrouted_share`,
`coast_residual`), which repeat on every row; read them from
`fct_exposure_summary`.

| Column | Type | Definition | Plain English |
|---|---|---|---|
| `basket` | text | Basket | |
| `canonical_product_id` | text | From hs_bridge on `hs6_code` and `hs_version` | |
| `hs6_code` | text | HS6 code | |
| `hs_version` | text | `H5` or `H6` | |
| `year` | integer | Calendar year | |
| `chokepoint_id` | text | PortWatch chokepoint ID | All 28, including those no route crosses |
| `chokepoint_name` | text | PortWatch chokepoint name | |
| `threshold_km` | integer | 50, 100, 200 or 300 | How close a route must pass to count as crossing. 200 is the headline |
| `weighting` | text | `export_share` or `vessel_count` | |
| `dest_coast` | text | `west`, `east`, `gulf` or `national` | |
| `exposure` | numeric | Modelled share of the code-year's general import value | Share of all US imports of the code whose shortest sea route passes this chokepoint. The dashboard shows 200km rows at 1% or more |

---

Lineage: `dbt docs generate` (`make dbt-docs`) renders the full graph
from raw sources to these marts. Formula and assumptions:
[`07_assumptions_limitations.md`](07_assumptions_limitations.md) §2.
