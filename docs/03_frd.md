# Functional Requirements: Semiconductor and Rare Earth Supply Chain Risk

What the system does to satisfy each business requirement in
[`02_brd.md`](02_brd.md). Written after the build, from the code and
[`07_assumptions_limitations.md`](07_assumptions_limitations.md) §2.1, so
it describes what exists. Every FR traces back to a BR here and forward
to a test and UAT case in
[`05_traceability_matrix.md`](05_traceability_matrix.md). Dashboard
acceptance cases are in [`06_uat_plan.md`](06_uat_plan.md).

BRs with no FR (BR-14 to BR-19, BR-23, BR-25, BR-27) are not built; the
matrix says why.

## Ingestion and landing

| FR | BR | What the system does | Where it lives | Acceptance criteria |
|---|---|---|---|---|
| FR-01 | BR-01, BR-03, BR-20, BR-28, BR-29 | Pulls annual US imports by partner and HS6 from UN Comtrade for 2018-2025, each year in its native HS vintage, plus the partner reference list for names and ISO3 | `ingest/comtrade.py`, `ingest/config.py` | `raw.comtrade_imports` 9,142 rows; `raw.comtrade_partners` 310 rows. Raises on auth failure or any non-200 and writes no file. Key read from the environment only. A rerun with the cache on disk makes zero calls |
| FR-02 | BR-07, BR-20, BR-28, BR-29, BR-31 | Pulls US Census imports by country (general, air, vessel and containerized value) and vessel imports by US port, one call per code over the full monthly range, plus the Schedule D port list and Schedule C country list | `ingest/census.py` | `raw.census_hs_annual` 130,006 rows; `raw.census_porths_vessel` 137,080 rows. Same fail-loud and cache rules as FR-01 |
| FR-03 | BR-08, BR-20, BR-29 | Pulls the PortWatch chokepoints database, ports database and daily chokepoint transits | `ingest/portwatch.py` | `raw.portwatch_chokepoints` 28 rows; `raw.portwatch_chokepoint_transits` 78,764 rows. ArcGIS errors inside HTTP 200 bodies are raised, not written |
| FR-04 | BR-21, BR-26 | Creates the raw tables and loads every cached file into Postgres `raw.*` as text, unchanged | `db/schema.sql` (`make schema`), `ingest/load.py` (`make load`) | `make schema` is idempotent (no DROP; reruns change no rows). Raw row counts match FR-01 to FR-03 and FR-10 |

## Products and concentration

| FR | BR | What the system does | Where it lives | Acceptance criteria |
|---|---|---|---|---|
| FR-05 | BR-05, BR-12, BR-13, BR-30, BR-32, BR-33 | Maps every HS6 code that ever represented a product to a canonical product across the 2021/2022 HS break, with a code status (active, retired_2021, introduced_2022) and a stated basis per row | `ingest/hs_bridge.py` from `manual/basket_codes.csv`, `manual/bridge_overrides.csv` and the UN correlation workbook -> `generated/hs_bridge.csv` | 854140 maps to 854141/142/143/149 and 854150 to 854151/159, the latter by an override that states its value-continuity evidence. `assert_h6_boundary_year_matches_bridge` passes |
| FR-06 | BR-02, BR-03, BR-05 | Computes each partner country's share of US import value per canonical product per year, summing across the product's codes first. Excludes the World row; reads partner 490 as Taiwan | `stg_comtrade`, `stg_comtrade_partners`, `fct_supplier_share` | Shares sum to 1 per product-year (`assert_supplier_shares_sum_to_one`); every partner has a name (`assert_comtrade_partners_matched`); World equals the sum of partners in raw (`assert_comtrade_partners_sum_to_world`) |
| FR-07 | BR-01, BR-02, BR-05, BR-06, BR-12 | Computes HHI (0-10,000), effective suppliers (10,000 / HHI), top supplier and share, top 3 share and supplier count per canonical product per year | `fct_concentration` | 176 rows (22 products x 8 years), unique on product-year. HHI within 0-10,000 (`assert_hhi_between_0_and_10000`). 280530 and 850511 are separate products |

## Mode, coast and routing

| FR | BR | What the system does | Where it lives | Acceptance criteria |
|---|---|---|---|---|
| FR-08 | BR-09, BR-31 | Splits each code's Census import value by country and year into general, air, vessel, containerized vessel and land residual, from December year-to-date detail rows only | `stg_census_hs`, `int_census_country_mode` | Unique on code x country x year; value columns not null. The `'-'` grand-total row is excluded |
| FR-09 | BR-31, BR-34 | Splits each code's vessel value by landing coast (west, east, gulf) through the Census district to coast map, keeping the residual that lands elsewhere | `stg_census_porths_vessel`, `int_coast_shares`, `manual/district_coast_map.csv` | Coast totals reconcile to the port table (`assert_coast_total_ves_val_matches_porths`); `coast` in (west, east, gulf) |
| FR-10 | BR-08 | Routes every PortWatch port with container traffic to one US port per coast along the shortest sea path and records the minimum distance to each of the 28 chokepoints. Portless countries route through a named gateway | `ingest/routing.py` -> `generated/routes.csv`, `generated/routing_matrix.csv`; `manual/landlocked_gateways.csv`, `manual/us_destination_ports.csv` | 3,759 routes over 1,253 ports; 105,252 matrix rows. Every weighted port is routed to every coast (`assert_weighted_ports_routed_to_every_coast`) |
| FR-11 | BR-08 | Weights each port within its country by PortWatch export share (headline) and by container vessel count (sensitivity) | `stg_portwatch_ports`, `int_port_weights` | Weights sum to 1 per country and weighting (`assert_port_weights_sum_to_one`) |
| FR-12 | BR-08, BR-10 | Marks a route as crossing a chokepoint when it passes within 50, 100, 200 or 300km, then rolls crossings up to a weighted crossing share per country, coast, chokepoint, threshold and weighting | `int_route_crossings`, `int_country_crossing_share`; thresholds in the dbt var `crossing_thresholds_km` | Crossing share within 0-1 (`assert_crossing_share_between_0_and_1`) |

## Exposure and the 2x2 mart

| FR | BR | What the system does | Where it lives | Acceptance criteria |
|---|---|---|---|---|
| FR-13 | BR-07, BR-09, BR-34 | Computes exposure per HS6 code, year, chokepoint, threshold, weighting and landing coast: each country's containerized value times its crossing share, over the code's total import value by all modes. Zeros are kept | `fct_exposure` | 172,032 rows, unique on the grain. Exposure never exceeds vessel coverage (`assert_exposure_within_vessel_coverage`, `assert_national_exposure_within_coast_coverage`). Never summed across chokepoints |
| FR-14 | BR-10, BR-24, BR-31, BR-34 | Builds one 2x2 point per HS6 code, year, weighting and coast: the largest single-chokepoint exposure at 200km over the risk set (Suez, Bab el-Mandeb, Panama, Hormuz, Taiwan Strait) with its name, the same chokepoint at 100 and 300km, the all-28 maximum for drilldown, vessel coverage, unrouted share, coast residual and the product's HHI | `fct_exposure_summary`, `manual/chokepoint_risk_set.csv` | 1,536 rows. Every code-year present (`assert_exposure_summary_covers_coast_shares`); risk set names match PortWatch (`assert_chokepoint_risk_set_matched`). Ties break on exposure then name; a zero maximum is labelled `none` |
| FR-15 | BR-21, BR-22 | Writes the four marts to CSV for Tableau, ratios rounded to 6 decimals, each file written whole or not at all | `ingest/export.py` (`make export`) -> `exports/*.csv` | Four files: `fct_exposure_summary`, `fct_supplier_share`, `fct_concentration`, `fct_exposure` (without its per code-year diagnostics) |

## Dashboard (Tableau Public, built by hand)

| FR | BR | What the system does | Where it lives | Acceptance criteria |
|---|---|---|---|---|
| FR-16 | BR-22, BR-24 | Five parameters drive all four sheets together: Product, Year (default 2025), Coast (default national), HHI line (default 4,000), Exposure line (default 25%). Weighting is fixed to export share | Tableau parameters | Changing any parameter updates every sheet that uses it. Tooltips show no aggregation asterisk; no Keep Only / Exclude buttons |
| FR-17 | BR-24 | The product is set from the Product dropdown or by clicking a point on the 2x2 | Tableau parameter action on the 2x2 | Clicking a point sets the dropdown to that HS6 code |
| FR-18 | BR-01, BR-04, BR-09, BR-24, BR-31, BR-33, BR-34 | 2x2 scatter: one point per HS6 code for the selected year and coast. x = HHI on a fixed 0-10,000 axis, y = risk-set exposure on a fixed 0-100% axis, labelled with its chokepoint and as modelled. Lines from the HHI and Exposure parameters. Tooltip carries effective suppliers and vessel coverage. Product names from a CASE on `hs6_code` | 2x2 sheet | 26 points in 2025, 22 in 2018. A code absent in a year shows no point |
| FR-19 | BR-10, BR-24 | Assigns each point a quadrant, checked in this order: "Distance sensitive" when exposure at 100km and at 300km fall on opposite sides of the Exposure line; "Buffer stock + second supplier" when HHI and exposure are both at or above their lines; "Qualify second supplier" for HHI only; "Hold buffer stock" for exposure only; "Monitor" for neither | Tableau calculated field `Quadrant` | Labels exactly as listed. 2025 national at defaults: 1 / 2 / 5 / 18 / 0 |
| FR-20 | BR-02, BR-03, BR-05 | Top suppliers: the top 10 partner countries by share for the selected product's canonical product and year. HS2022 successors map to 854140 or 854150 | Top suppliers sheet; Tableau CASE on the six successors | Shares match `fct_supplier_share` |
| FR-21 | BR-01, BR-04, BR-06, BR-12 | HHI trend: HHI for the selected canonical product for every year 2018-2025, with the HHI line | HHI trend sheet | Eight years, no gap across 2021/2022; line moves with the HHI parameter |
| FR-22 | BR-07, BR-11, BR-34 | Chokepoints: the top 10 chokepoints at 200km with exposure of 1% or more for the selected code, year and coast, risk set coloured apart, titled "do not add these up" | Chokepoints sheet | Values match `fct_exposure` at 200km, export share |
| FR-23 | BR-24 | Coast control: national (blended by coast share) or west, east or gulf (that coast's share set to 1). HHI does not change with coast | Coast parameter over `dest_coast` | Switching coast moves exposure only |
