# UAT Plan: Semiconductor and Rare Earth Supply Chain Risk

Acceptance evidence for the functional requirements in
[`03_frd.md`](03_frd.md), in two parts: the automated dbt tests that
guard the data, and manual cases run against the published Tableau
dashboard. [`05_traceability_matrix.md`](05_traceability_matrix.md) links
each case back to its BR and FR.

## Part A: automated (dbt)

`make dbt-test`: 97 tests, 13 custom (`dbt/tests/`) and 84 schema tests
(`schema.yml`). **Status: Passed, 97 of 97, 2026-09-26.**

| What the tests protect | Tests | Custom tests | FR |
|---|---|---|---|
| Source reconciliation: raw data agrees with itself and the reference lists | 5 | `assert_comtrade_partners_sum_to_world`, `assert_comtrade_partners_matched`, `assert_coast_total_ves_val_matches_porths`, `assert_h6_boundary_year_matches_bridge`, `assert_chokepoint_risk_set_matched` | FR-05, FR-06, FR-09, FR-14 |
| Mode split: one row per code, country and year, no null values (`int_census_country_mode`) | 13 | | FR-08 |
| Coast split: one row per code, year and coast, coast in the accepted set (`int_coast_shares`) | 10 | | FR-09 |
| Port weights: unique, accepted weighting and source, sum to 1 (`int_port_weights`) | 9 | `assert_port_weights_sum_to_one` | FR-11 |
| Route crossings: unique per port, coast, chokepoint and threshold (`int_route_crossings`) | 7 | | FR-12 |
| Country crossing share: unique, within 0-1 (`int_country_crossing_share`) | 8 | `assert_crossing_share_between_0_and_1` | FR-12 |
| Routing coverage: every weighted port routed to every coast | 1 | `assert_weighted_ports_routed_to_every_coast` | FR-10 |
| Supplier shares: unique per partner and per rank, sum to 1 (`fct_supplier_share`) | 12 | `assert_supplier_shares_sum_to_one` | FR-06 |
| Concentration: unique per product-year, HHI within 0-10,000 (`fct_concentration`) | 4 | `assert_hhi_between_0_and_10000` | FR-07 |
| Exposure: unique on the full grain, accepted coast and weighting, no nulls, never above vessel or coast coverage (`fct_exposure`) | 18 | `assert_exposure_within_vessel_coverage`, `assert_national_exposure_within_coast_coverage` | FR-13 |
| 2x2 mart: unique per code, year, weighting and coast, every flow_ and risk_ column populated (`fct_exposure_summary`) | 9 | | FR-14 |
| 2x2 completeness: every code-year with coast shares has a 2x2 row | 1 | `assert_exposure_summary_covers_coast_shares` | FR-14 |
| **Total** | **97** | **13** | |

## Part B: dashboard acceptance cases

Defaults unless stated: Year 2025, Coast national (US average), HHI line
4,000, Exposure line 25%. Every expected value was checked against
Postgres (`analytics.fct_*`) on 2026-09-26.

| ID | FR | Steps | Expected result | Status |
|---|---|---|---|---|
| UAT-01 | FR-18 | Open the dashboard. Count points on the 2x2. Set Year to 2018 | 26 points in 2025; 22 in 2018 | To run on the published dashboard |
| UAT-02 | FR-18, FR-19 | Hover 280530 on the 2x2 | HHI 6,924; exposure 46.0%, Panama Canal; "Buffer stock + second supplier" | To run on the published dashboard |
| UAT-03 | FR-19 | Read the quadrant of every point | "Qualify second supplier": 850511, 284610. "Hold buffer stock": 854143, 854190, 848610, 848630, 284690. "Monitor": 18 codes. "Distance sensitive": 0 | To run on the published dashboard |
| UAT-04 | FR-19, FR-23 | Set Coast to West | 280530 becomes "Qualify second supplier" (Taiwan Strait 11.2%). 284690, 848610, 848630 become "Monitor". 854143 (Taiwan Strait 33.7%) and 854190 (Taiwan Strait 55.5%) stay "Hold buffer stock". HHI values do not move | To run on the published dashboard |
| UAT-05 | FR-16, FR-18, FR-19 | Drag the HHI line from the default 4,000 to 3,750. Then reset it to 4,000 | At 3,750, 284690 (HHI 3,764) becomes "Buffer stock + second supplier"; no other point changes. At 4,000 it returns to "Hold buffer stock" | To run on the published dashboard |
| UAT-06 | FR-19 | Set Year to 2023, Coast to West | 848610, 854142, 854190 are "Distance sensitive" (Taiwan Strait below 25% at 100km, above at 300km) | To run on the published dashboard |
| UAT-07 | FR-20 | Select 280530. Read Top suppliers. Set Year to 2023 | 2025: China 82.5%, Rep. of Korea 9.2%, United Kingdom 4.2%. 2023: China 98.7% | To run on the published dashboard |
| UAT-08 | FR-21 | Select 280530. Read HHI trend. Move the HHI line | 6,157 (2018), 9,749 (2023), 6,924 (2025), eight years with no gap. The reference line moves with the HHI parameter | To run on the published dashboard |
| UAT-09 | FR-22 | Select 854143. Read Chokepoints | Gibraltar Strait 52.1% (not risk set), Suez Canal 52.0% and Bab el-Mandeb Strait 51.8% (risk set); 10 bars, all at 1% or more | To run on the published dashboard |
| UAT-10 | FR-17, FR-20 | Pick 854190 from the Product dropdown | Top supplier Viet Nam 40.4%; HHI 2,138 | To run on the published dashboard |
| UAT-11 | FR-17 | Click the Solar panels point on the 2x2 | Product dropdown shows 854143 | To run on the published dashboard |
| UAT-12 | FR-18, FR-20 | Select 854143. Set Year to 2018 | No 854143 point on the 2x2 (the code starts in 2022). Top suppliers show the pre-2022 family, 854140 | To run on the published dashboard |
| UAT-13 | FR-16 | Change Year | All four sheets update together | To run on the published dashboard |
| UAT-14 | FR-16 | Hover points and bars on every sheet | No tooltip shows "*"; no Keep Only / Exclude buttons | To run on the published dashboard |
