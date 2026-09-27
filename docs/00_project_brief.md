# PROJECT BRIEF: Semiconductor and Rare Earth Supply Chain Risk

> **Baselined, superseded where the code differs.** The current record is [`docs/07_assumptions_limitations.md`](07_assumptions_limitations.md) and [`README.md`](../README.md). Not built: event study (D-7), Excel scenario workbook (D-10), GitHub Actions scheduled refresh, PortWatch data-quality dbt tests.

**Owner:** Akash A
**Repo:** `semiconductor-rare-earth-supply-chain-risk`
**Status:** Verification complete, build in progress
**Last updated:** 2026-09-18

> Planning phase: this file was the source of truth.
> Build phase (current): the repo is the source of truth. This document is
> reconciled to it at milestone boundaries, not continuously. A build finding
> that contradicts this document does not block the build. It gets a line in
> docs/FINDINGS.md and the code proceeds.
> Update the Decision Log when a real choice gets made. Section 14 is this
> document's change history.
> Never put API keys in this file. Keys live in .env only.

---

## 0. Current state

Updated: 2026-09-22
Phase: build, dbt transform

Done: 7 reference CSVs committed and loaded as seeds. Docker + Postgres 16
  on port 5433 (a system Postgres owns 5432, leave it alone). Raw layer
  loaded: comtrade 9,142, census_hs 130,006, porths_annual 119,900,
  porths_vessel 137,080, pw_transits 78,764, pw_geo 28. dbt scaffolded,
  5 staging models built clean: stg_comtrade 8,950, stg_census_hs 91,081,
  stg_census_porths_vessel 134,776, stg_portwatch_transits 78,764,
  stg_portwatch_chokepoints 28.

Next: intermediate models (hs_bridge join, mode shares, partner shares),
  then fct_concentration and fct_exposure, then CSV export for Tableau,
  then dashboard, then README.

Open: port coast classification lives in analysis/census_mot_spike.py as a
  documented district map with per-port overrides. Content is sound and
  verified. Moving it to a committed CSV seed is a pending inspectability
  improvement, not a correctness fix.

Deadline: tonight, 2026-09-22.

---

## 1. Thesis

For a defined set of critical imported products, which ones does the United States depend on a small number of foreign suppliers for, and how exposed is that supply to a maritime chokepoint disruption?

The output is a supplier concentration and chokepoint exposure model, delivered as a tested data pipeline, a public dashboard, and a full set of business analysis artifacts.

The two baskets answer different halves of that question, with one large exception inside the first. Semiconductors and SME are 75.1 percent air by value, rising to 83.5 percent once photovoltaic codes are set aside, so their story is concentration. The exception is 854142 and 854143, solar cells and modules, which are 11 percent of that basket's value but 90.8 percent containerized vessel, and 854143 alone is $49.0B and the most vessel dominant code in the project. Rare earths and magnets are 58.4 percent containerized vessel on $5.0B. So the seaborne exposure story is solar first at $54.6B, magnets second at $5.0B, and integrated circuits barely at all: 854231 moves 0.8 percent by vessel against $196.73B total. The asymmetry is a measured finding, not a gap in the build.

## 2. Stakeholder framing (fictional, but treated as real)

**Stakeholder:** Supply chain risk committee at a mid-size US electronics manufacturer.

**Decision being supported:** Ahead of annual supplier contract renewals, the committee must decide where to qualify a second supplier and where to hold buffer inventory.

**What they need to know:**
1. Which inputs are dependent on a small number of foreign suppliers
2. Which of those dependencies are exposed to a maritime chokepoint closure
3. How that exposure has changed over time

Every requirement traces back to this decision. If something in the build does not serve it, cut it.

---

## 3. Scope declaration

| Dimension | In scope | Out of scope |
|---|---|---|
| Reporter (importer) | United States only | All other importers |
| Partner (exporter) | All partners | None |
| Products | 2 baskets, 22 verified HS6 codes, listed in `data/reference/basket_selection.csv` | All other HS codes |
| Classification | HS2017 (H5) for 2018 to 2021 and HS2022 (H6) for 2022 onward, both required in the first release | Vintages before 2017 |
| Years | 2018 to 2025 | Partial year 2026 |
| Maritime data | All 28 chokepoints ingested; crossings computed, not assumed | 2,065 individual ports |
| Flow | Imports | Exports, re-exports |

**Baskets:**

1. **Semiconductors and semiconductor manufacturing equipment.** HS 8541, 8542, 8486 families. 18 codes. Carries the concentration story. Exposure is published but covers the seaborne minority of its flow.
2. **Rare earths and permanent magnets.** HS 280530, 284610, 284690, 850511. 4 codes. Carries both concentration and exposure.

The original estimate of roughly 35 codes was arithmetic error, not a filter. The 8541, 8542, 8486 and 2846 families are exhaustively enumerated at HS6 and total 22 with 280530 and 850511. No candidate code was dropped for low value. All 22 were verified against the live Comtrade code list and cleared the value floor.

`basket_selection.csv` also records four adjacent codes considered and excluded, with a basis per row: 850519 (other permanent magnets), 253090 (rare earth ores), 360690 (ferro-cerium), 903082 (semiconductor test instruments).

**Analytical note on magnets, resolved.** The brief originally hypothesised that downstream magnet manufacturing (8505.11) is more concentrated than raw rare earth metals (2805.30). Measurement disproved it. In 2023, 280530 reaches HHI 9,749 at 98.7 percent China against 850511 at HHI 6,413 and 79.8 percent China. Caveat carried wherever this appears: 280530 sits on a value base under $50M a year, so the ranking is real but the base is thin. The disproven hypothesis is kept in the record rather than deleted, because the point of stating it in advance was to be able to be wrong about it.

---

## 4. Data sources

### UN Comtrade
- **What:** Bilateral trade flows by reporter, partner, HS code, year
- **Access:** Free tier, requires registered API key
- **Limits:** Up to 100K records per call, up to 500 calls per day
- **Client:** `comtradeapicall` (official UN Python package)
- **Key storage:** `.env`, gitignored. Subscription name `import-concentration-risk`
- **Operational trap:** Free-tier keys may be regenerated ad hoc under the fair usage policy, and free users must log into the portal regularly to keep keys active. Ingest must fail loudly on 401, never silently write an empty file. Log into the portal every couple of weeks.
- **Fair usage:** Do not scrape the UI. Do not register multiple accounts to dodge the daily limit. Throttle and cache.
- **No-key fallback:** `public - v1` endpoint returns 500 records with no key. Sufficient for building and testing the ingest script.
- **Known trap:** the World aggregate row (partner code 0) must be filtered out of share calculations, at the staging layer rather than at ingest. Description columns return null, so filter on codes not text, and pass `includeDesc=True`.

### US Census international trade
- **What:** Monthly US imports by HS6 with air, vessel, and containerized vessel value, plus port of entry
- **Access:** Free, requires registered API key, stored as `CENSUS_API_KEY` in `.env`
- **Used for:** Mode of transport shares and coast of entry shares, which enter the exposure formula as measured multipliers
- **Why it exists:** Comtrade reports TOTAL MOT only for the US. Without Census there is no measured basis for splitting import value into air, vessel, and land.
- **Operational traps:** `SUMMARY_LVL` must be filtered to `DET` and the `"-"` grand total sentinel excluded, since it is also tagged `DET`. Unfiltered, regional groupings such as ASIA and PACIFIC RIM double count against per-country rows: 854231 in 2018 sums to $125.4B unfiltered against a true $21.6B. Comma joined commodity codes are rejected with HTTP 204, so one call per code covering the full monthly range. Port of entry distribution must be computed on vessel value only, or the top ports come back as LAX, SFO, Anchorage and Sea-Tac, which are airports.

### IMF PortWatch
- **What:** Daily transit calls and trade volume estimates for 28 maritime chokepoints, derived from satellite AIS signals on ~90,000 ships, plus chokepoint point coordinates from a separate spatial layer
- **Access:** Free, no key. Served via ArcGIS FeatureServer, also downloadable as CSV/GeoJSON
- **Endpoint pattern:** `services9.arcgis.com/weJ1QsnbMYJlCHdG`, layer `Daily_Chokepoints_Data`, filtered by `portid`
- **Pagination:** Standard ArcGIS `resultOffset` / `resultRecordCount`
- **Refresh:** Weekly, Tuesdays ~9 AM ET
- **No bulk endpoint:** iterate over chokepoint IDs

### searoute (Eurostat network)
- **What:** Shortest sea route between two points, computed over a pre-built ocean mesh with Dijkstra
- **Access:** Python package, computed locally, no API
- **Used for:** Determining which chokepoints a route between two ports passes near

### Reference data
- **UN/LOCODE, improved republication**: origin and destination port coordinates. Official UN/LOCODE has no coordinates for several ports including Kaohsiung; the republication fills those gaps from OpenStreetMap and the fill is recorded per row.
- **Census Schedule D port and district codes**: classifying US ports of entry into coastal regions and land borders. Classification by port name fails, because CBP districts mix seaports with land crossings under one district number.
- **UN Stats HS correlation tables**: source for the concordance bridge. **Not authoritative.** See section 6.
- **USGS Mineral Commodity Summaries / US Critical Minerals List**: grounds the rare earth basket selection
- **DOE Critical Materials Assessment**: same purpose
- **Commerce semiconductor supply chain review**: grounds the semiconductor basket selection
- **US DOJ/FTC Merger Guidelines**: source for HHI concentration thresholds. Cite the version and year used.

All API responses cache under `data/raw/` on first pull and are read from cache on rerun. `data/raw/` is immutable and gitignored. A rerun costs zero API calls.

---

## 5. Documented data quality rules (PortWatch published anomalies)

These are disclosed by the source. Encode each as a rule and a dbt test. This section is the most transferable part of the project.

| Issue | Handling |
|---|---|
| Blackout dates: 2022-05-12, 2023-02-14, 2024-01-09 | Exclude from clean mart; test asserts zero rows |
| GPS jamming / spoofing / vessels going dark near Strait of Hormuz | Flag and caveat; do not treat Hormuz volumes as reliable |
| Transponders switched off in sanctioned regions (Red Sea, Iran, Russia, Ukraine, Venezuela) | Flag affected chokepoints and periods |
| 2021 receiver coverage expansion caused sustained step change at Gwangyang and Malacca | Flag as series break; do not interpret as real growth |
| Strait of Hormuz boundary revised Feb 2026 | Historical series may not be comparable across the change; pin data version |

Structural rules verified in the data: `n_cargo` equals the sum of its components exactly across all 78,764 rows, `n_total` equals `n_cargo + n_tanker` exactly, and the vessel type breakdown exists from the first date for all 28 chokepoints with no schema cutover.

---

## 6. Known hard problems

**HS concordance.** Codes split, merge, and retire across revisions (1996, 2002, 2007, 2012, 2017, 2022). Solved with a bridge table held as data, not as SQL. US data is native H5 through 2021 and H6 from 2022, so the bridge is a first release requirement rather than a backward-extension enhancement. Querying H5 for 2022 or later returns zero rows.

**Published concordances are not authoritative.** The UN Stats HS2022 to HS2017 correlation table names 851712 (cellular telephones) as sole predecessor of both 854151 and 854159, the two HS2022 successors of 854150, which has no trade-value support and no plausible mechanism. Checked for a parsing artifact and ruled out: the Conversions tab is structurally one predecessor per code, with zero merged cells and zero continuation rows. Resolved empirically instead, by Census value continuity across the 2021/2022 break: 854150 at $825.9M in 2021 against 854151 plus 854159 at $819.9M in 2022, a 0.7 percent gap. Every mapping the bridge relies on is now validated against value continuity before use. Full derivation in `docs/07_assumptions_limitations.md` sections 6.1 and 6.2.

**Product-to-chokepoint routing.** No source links product flows to chokepoint transits. Routing is computed rather than assumed: shortest sea route from a UN/LOCODE sourced origin port to a US coast, over the Eurostat ocean mesh via Dijkstra, intersected against PortWatch chokepoint coordinates. Proximity is the true nearest point on the route line, measured in an azimuthal equidistant projection centred on the chokepoint so planar distance equals great circle distance. The only remaining free parameter is the 200km threshold, sensitivity tested at 50, 100, 200 and 300km. What this still ignores: routing substitution, transshipment, carrier alliance routing, and the fact that one representative port stands in for a whole country's exports.

**Basket routing relevance, measured.** The original assumption that both baskets route via Malacca and the South China Sea is wrong. East Asia to US West Coast crosses the open Pacific. Across 30 tested routes, Panama is crossed 10 times, Gibraltar and Windward Passage 7 each, Malacca 6. Gibraltar, Suez and Bab el-Mandeb appear only for European, Israeli and Indian origins. The Pacific chokepoints that matter for these baskets are Taiwan Strait, Korea Strait, Tsugaru and Luzon. The Strait of Hormuz is crossed by zero of 30 routes and is overwhelmingly tanker traffic, so it is retained only as a contrast case. Two independent lines of evidence, route geometry and vessel mix, reach the same conclusion about Hormuz.

---

## 7. Architecture decisions

**Carry `hs_version` as a column** through raw and staging. Every row knows its classification vintage.

**Bridge table as data**, at `data/reference/hs_bridge.csv`:
```
canonical_product_id, hs_version, hs6_code, code_status, basket, notes, vintage_break_year
```
One canonical product maps to many HS codes across vintages. `code_status` is `active`, `retired_2021` or `introduced_2022`, so a mart can tell a structural non-event apart from a data quality gap. A retired or not-yet-introduced code's missing years must never render as missing data.

**Marts group by `canonical_product_id`, never by raw HS code.** This is what makes backward extension cheap: add rows to the CSV, widen the year range, `dbt build`. Zero SQL changes.

**Concentration rolls up, exposure does not.** Concentration is computed per canonical product, because who supplies a product survives aggregation. Exposure is computed per commodity code, because the vessel share and coast share multipliers are measured per code and can diverge sharply between successors of the same canonical product. 854140's four HS2022 successors range from 2.75 percent to 95.2 percent containerized vessel, so a blended coverage figure for that canonical product would describe no physical object. Exposure is published per code, grouped for display under its canonical product. 854150's two successors differ by 0.02 percentage points and would not have required this, but the rule is stated once and applied everywhere rather than case by case.

**Never hardcode** classification vintage or year range in SQL.

**Raw ingest is unfiltered.** All 28 chokepoints and all verified codes land raw. Relevance filtering happens in `staging/`, never at ingest. A chokepoint crossed by zero routes is published as a computed zero, not dropped.

**Land trade is excluded from exposure, not from concentration.** Mexico and Canada imports are 95.5 and 74.8 percent land respectively. Land value has no maritime chokepoint exposure and is removed from the exposure denominator. It stays in every concentration measure. Air value is treated the same way: measured, removed from the denominator, never routed.

**Python computes, dbt transforms.** Python does ingest, the searoute routing computation, and event study arithmetic. Every share, index, and join lives in dbt. `routing_matrix.csv`, `hs_bridge.csv` and `basket_selection.csv` are Python or hand curated outputs committed as reference data, which is what keeps them inspectable and editable without touching logic.

**`data/raw/` is immutable.** Never edited in place. Reference data in `data/reference/` is committed; raw data is gitignored.

---

## 8. Stack

| Layer | Tool | Why |
|---|---|---|
| Ingest | Python: `comtradeapicall`, `requests`, `pandas`, `pyarrow`, `openpyxl` | Official client; ArcGIS and Census need plain requests; openpyxl reads the UN correlation workbook |
| Routing | Python: `searoute`, `shapely`, `pyproj` | Local computation, no API |
| Landing | PostgreSQL in Docker | Free, local, ARM-native, fast iteration |
| Transform | dbt Core | Lineage, tests, auto docs; primary technical differentiator |
| Analysis | Python: `pandas`, `numpy`, `matplotlib` | Event study and scenario arithmetic only |
| BI primary | Tableau Public | Free, native on M2, public URL to link from resume |
| BI secondary | Excel scenario workbook | Stakeholder leave-behind for non-licensed users |
| Orchestration | GitHub Actions | Weekly cron after Tuesday PortWatch refresh; dbt tests as gate |
| Env | `uv` + `.env` | Keys out of git |

**Deferred, not cancelled:** Streamlit interactive tool; Snowflake port (120-day trial, $400 credits, XS warehouse + 60s auto-suspend); Power BI (requires cloud Windows VM).

**Hardware constraint:** MacBook M2, 8GB RAM. Do heavy joins in SQL where Postgres manages memory, not in pandas. Do not run Docker plus a large pandas session plus a heavy browser simultaneously.

---

## 9. Repo structure

```
semiconductor-rare-earth-supply-chain-risk/
├── PROJECT_BRIEF.md
├── CLAUDE.md               # gitignored: the private working spec
├── README.md
├── .gitignore
├── .env.example            # COMTRADE_API_KEY, CENSUS_API_KEY
├── docs/
│   ├── 01_project_charter.md
│   ├── 02_brd.md
│   ├── 03_frd.md
│   ├── 04_data_dictionary.md
│   ├── 05_traceability_matrix.md
│   ├── 06_uat_test_plan.md
│   ├── 07_assumptions_limitations.md
│   └── decision_log.md
├── ingest/
│   ├── config.py
│   ├── comtrade.py
│   ├── census.py
│   ├── portwatch.py
│   ├── reference.py        # port and chokepoint coordinates, routing matrix
│   └── hs_bridge.py        # UN correlation workbook to bridge table
├── data/
│   ├── raw/                # gitignored, immutable
│   └── reference/          # committed
├── db/
│   └── schema.sql          # raw landing DDL, applied to Postgres before dbt runs
├── dbt/
│   ├── models/{staging,intermediate,marts}/
│   ├── tests/
│   └── dbt_project.yml
├── analysis/
├── viz/
└── .github/workflows/refresh.yml
```

`data/reference/` committed: `basket_selection.csv`, `hs_bridge.csv`, `routing_matrix.csv`, `mode_shares.csv`, `port_entry_shares.csv`, `port_coordinates.csv`, `chokepoint_coordinates.csv`

**dbt layer rules:**
- `staging/`: one model per source table. Rename, cast, unpivot. No joins, no aggregation. Prefix `stg_`.
- `intermediate/`: joins and business logic. Not consumed directly. Prefix `int_`.
- `marts/`: what BI reads. Prefix `fct_` and `dim_`.

---

## 10. Core measures

**HHI (Herfindahl-Hirschman Index):** sum of squared partner import-value shares, per canonical product per year. Scale 0 to 10,000. Thresholds sourced from current DOJ/FTC Merger Guidelines, version cited in the data dictionary. Where a canonical product spans several HS codes, sum partner values across codes first, then compute shares and HHI on the total. HHI of a combined product is not the average of its components' HHIs.

**Also report:** top supplier share, top-3 concentration, supplier count. HHI is analytically better; top supplier share is what a procurement person intuitively reads. Report both and explain why.

**Exposure score.** Per canonical product per chokepoint per year:

```
exposure = sum over partners of [
      partner_share_of_import_value           (Comtrade, measured)
    x containerized_vessel_share_of_that_code (Census, measured)
    x routing_weight(partner, chokepoint)     (searoute, computed)
]

routing_weight = sum over US coasts of [
      coast_share_of_that_code's_vessel_value (Census, measured)
    x 1 if the shortest sea route from that partner's representative port
        to that coast passes within 200km of the chokepoint, else 0
]
```

Every term is measured or computed. Air and land value are removed from the denominator rather than routed. The single judgement call is the 200km threshold. Exposure is still labelled as modelled wherever it sits beside a measured concentration figure, because the assumptions behind it remain untestable: that a shortest sea route resembles the route sailed, and that a radius around a point coordinate represents a strait.

**Vessel share coverage** is published beside every exposure figure, so a near-zero score for a basket that flies reads as a finding rather than a defect.

**Event study, candidates from crossed chokepoints only:**
- Panama, most crossed at 10 of 30 routes, and the 2023 to 2024 drought transit restrictions
- Suez and Bab el-Mandeb versus Cape of Good Hope from Nov 2023, clean substitution, but relevant only to European, Israeli and Indian origins in these baskets
- Taiwan Strait, most relevant to the magnet basket, watch vessel mix before committing

Malacca is demoted from the shortlist: 6 of 30 crossings and a known 2021 receiver coverage series break. Hormuz is excluded as an event study and kept only as the contrast case.

---

## 11. Deliverables

**Must ship:**
- Working ingest for all three API sources, reproducible from cold start
- Postgres landing schema
- dbt project: staging, intermediate, marts, 12 to 15 tests, generated lineage docs
- HHI and exposure marts
- Computed routing matrix, committed with every non-crossing included
- One event study
- Threshold sensitivity test at 50, 100, 200 and 300km
- Tableau Public dashboard at a live URL
- Excel scenario workbook (named parameter cells, data validation, two-variable Data Table, XLOOKUP, conditional formatting)
- All seven `/docs` artifacts
- README with screenshots and links

**Stretch:** Streamlit app; HS2012 backward extension.

**Later, separate weekends:** Snowflake port; Power BI report.

---

## 12. Framing for different audiences

The framework is product-agnostic. Baskets are rows in `dim_product`, not hardcoded logic. Say so in the README.

- **Semiconductor / hardware:** supplier concentration in the products they actually buy, plus the finding that most of it flies
- **Consulting:** unfamiliar domain, sourced data, defensible framework, documented assumptions, a published reference table caught wrong and corrected empirically, recommendation. Frame as a client engagement.
- **Tech:** lead with "concentration risk framework," not "trade data." HHI generalises to revenue concentration by customer, vendor concentration, marketplace seller concentration.
- **Financial services / risk:** counterparty and country risk, trade finance
- **Logistics and freight tech:** close to core business. Expect the routing method to be challenged, and lead with what it cannot do.

Pitch commercially (corporate supply chain risk), not geopolitically. Geopolitical framing points at defense and government employers, most of which require US Person status.

---

## 13. Repo hygiene

- The working spec (`CLAUDE.md`) and `.claude/` in `.gitignore`
- No co-author trailers or "Generated with" footers in commit messages
- `.env` gitignored before any key is ever written to it
- Squash or reword early history before the repo goes public
- Never read or write `.env`. Load config through `ingest/config.py` only
- Cache every API response to `data/raw/` on first pull. Never re-request data already on disk

---

## 14. Decision log

| Date          | Decision                                                                                   | Rejected alternative                                                                                                  | Reason                                                                                                                                                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-13    | US as sole reporter                                                                        | US + EU27 comparison                                                                                                  | Doubles data volume and concordance work for marginal analytical gain within a 5-day build                                                                                                                                                                                 |
| 2026-09-13    | Baskets: semis+SME, rare earths+magnets                                                    | Pharma APIs; substrates/advanced packaging                                                                            | Semis match referral network and SEMICON West; rare earths give the most portable and legible concentration story                                                                                                                                                          |
| 2026-09-13    | HHI as primary concentration measure                                                       | Top-supplier share alone                                                                                              | Top share cannot distinguish one dominant supplier from two; HHI can. Both reported.                                                                                                                                                                                       |
| 2026-09-13    | Static exposure score, dashboard filter                                                    | Parametrized Python scenario engine                                                                                   | Same analytical payload, roughly one day cheaper to build                                                                                                                                                                                                                  |
| 2026-09-13    | HS2017 first, HS2012 as enhancement                                                        | Full 1996-present concordance                                                                                         | Working pipeline by Friday matters more than range; bridge-table design makes extension cheap                                                                                                                                                                              |
| 2026-09-13    | Chokepoints only                                                                           | Include 2,065-port dataset                                                                                            | Ports add volume without serving the stakeholder decision                                                                                                                                                                                                                  |
| 2026-09-13    | Defer Snowflake and Power BI                                                               | Build on them now                                                                                                     | Neither improves the analysis; both cost setup time inside a 5-day window                                                                                                                                                                                                  |
| 2026-09-18    | Census added as a third source                                                             | Infer mode split from Comtrade                                                                                        | Comtrade reports TOTAL MOT only for the US. Without Census the air, vessel and land split is unmeasurable                                                                                                                                                                  |
| 2026-09-18    | Routing computed via searoute                                                              | Hand assigned routing matrix with stated basis per row                                                                | Removes the project's largest subjective input. The matrix becomes a computation with one stated parameter                                                                                                                                                                 |
| 2026-09-18    | 200km proximity threshold kept as a single global parameter, sensitivity tested            | Per-chokepoint thresholds scaled to each strait's real width                                                          | Scaling per chokepoint replaces one stated parameter with 28 hand-assigned ones, reintroducing the subjective input the computation removed                                                                                                                                |
| 2026-09-18    | HS bridge promoted to first release requirement                                            | Bridge as backward extension enhancement                                                                              | US data is H5 through 2021 and H6 from 2022. Without the bridge the series stops in 2021                                                                                                                                                                                   |
| 2026-09-18    | 854150's successors resolved empirically against trade value                               | Trust the UN Stats correlation table, or mark the code unresolved                                                     | The table names an unrelated telephone code as sole predecessor of both successors. Value continuity across the break closes at 0.7 percent. Marking it unresolved would have dropped an $825M code from 2022 onward                                                       |
| 2026-09-18    | Baskets framed asymmetrically                                                              | Symmetric concentration plus exposure for both                                                                        | Semis move 70 to 98 percent by air. Reporting their exposure as comparable to the magnet basket would misrepresent a measured finding as a model failure                                                                                                                   |
| 2026-09-18    | All 28 chokepoints ingested, filtered in staging                                           | Narrow scope to the 13 crossed chokepoints                                                                            | Raw stays faithful to source. Zero crossings is a published finding, not an exclusion                                                                                                                                                                                      |
| 2026-09-18    | Land trade excluded from exposure, retained in concentration                               | Exclude land origin countries entirely                                                                                | Mexico and Canada are real suppliers with real concentration. Only their maritime exposure is undefined                                                                                                                                                                    |
| 2026-09-18    | Exposure computed at HS6 grain, concentration at canonical product grain                   | Blend successor mode shares into one canonical coverage figure, or split 854140 into two canonical products from 2022 | 854140's successors span 2.75 to 95.2 percent containerized vessel. A blended figure violates BR-31, which exists so a coverage number means something. Splitting the canonical product would break the pre-2022 series, since the H5 parent cannot be split retroactively |
| 2026 - 09- 24 | Added UN Comtrade partnerAreas.json (keyless reference file, 310 partners) as a raw source | raw.comtrade_partners                                                                                                 | /get/C/A/HS returns partner codes only; gives partner ISO3, name and group flag for fct_supplier_share. Partner 490 "Other Asia, nes" overridden to Taiwan/TWN in manual/comtrade_partner_overrides.csv.                                                                   |

---

## 15. Open questions

Resolved during Verification, evidence in `docs/07_assumptions_limitations.md`:
- All 22 HS6 codes verified against the live Comtrade code list
- Latest available year confirmed as 2025
- Classification break located: H5 through 2021, H6 from 2022
- Chokepoints the baskets actually transit, computed not assumed
- 854150's HS2022 successors resolved against trade value

Still open:
- [ ] Record the current DOJ and FTC Merger Guidelines version and its HHI threshold bands
- [ ] Fill `candidate_source`, `us_net_import_reliance_pct` and `decision_basis` in `basket_selection.csv` from the USGS, Interior and Commerce reference documents
- [ ] Sensitivity test the 200km threshold at 50, 100, 200 and 300km when the exposure mart is built
- [ ] Encode the vintage-break continuity check as a dbt test
- [ ] Choose the event study after inspecting PortWatch series for the shortlisted chokepoints
- [ ] Run the concentration series across all years now that the bridge exists. Whether concentration worsened after the 2025 Chinese export restrictions is still unmeasured
- [ ] Investigate 854151's jump from $18M to $179M in 2025: real shift or classification migration
- [ ] Decide whether photovoltaic codes 854142 and 854143 stay inside the semiconductor basket or become a named third sub basket. They entered by exhaustive HS family enumeration, are $54.6B, and carry most of the project's seaborne exposure
