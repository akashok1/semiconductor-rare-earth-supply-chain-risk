# PROJECT BRIEF — Trade Chokepoint Exposure

**Owner:** Akash A
**Repo:** `trade-chokepoint-exposure`
**Status:** Setup / Day 0
**Last updated:** 2026-09-13

> This file is the source of truth. Anything not written here does not exist.
> Update the Decision Log every time a real choice gets made.
> **Never put API keys in this file.** Keys live in `.env` only.

---

## 1. Thesis

For a defined set of critical imported products, which ones does the United States depend on a small number of foreign suppliers for, and how exposed is that supply to a maritime chokepoint disruption?

The output is a supplier concentration and chokepoint exposure model, delivered as a tested data pipeline, a public dashboard, and a full set of business analysis artifacts.

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
| Partner (exporter) | All partners | — |
| Products | 2 baskets, ~35 HS6 codes total | All other HS codes |
| Classification | HS2017 (H5) initially; extend to HS2012 (H4) as enhancement | Pre-2012 vintages |
| Years | 2018 to latest available initially | Pre-2018 initially |
| Maritime data | 28 chokepoints | 2,065 individual ports |
| Flow | Imports | Exports, re-exports |

**Baskets:**

1. **Semiconductors and semiconductor manufacturing equipment** — HS 8541, 8542, 8486 families
2. **Rare earths and permanent magnets** — HS 2805.30, 2846 family, 8505.11

> Starting HS codes are candidates only. Verify every one against the live Comtrade code list on Day 1 before committing them to `dim_product`.

**Analytical note on magnets:** China's concentration in downstream magnet manufacturing (8505.11) is generally more extreme than in raw rare earth metals (2805.30). If the data shows that gap, it is the most interesting finding in the basket. Do not assume it; measure it.

---

## 4. Data sources

### UN Comtrade
- **What:** Bilateral trade flows by reporter, partner, HS code, year
- **Access:** Free tier, requires registered API key
- **Limits:** Up to 100K records per call, up to 500 calls per day
- **Client:** `comtradeapicall` (official UN Python package)
- **Key storage:** `.env`, gitignored. Subscription name `trade-chokepoint-exposure`
- **Operational trap:** Free-tier keys may be regenerated ad hoc under the fair usage policy, and free users must log into the portal regularly to keep keys active. Ingest must fail loudly on 401, never silently write an empty file. Log into the portal every couple of weeks.
- **Fair usage:** Do not scrape the UI. Do not register multiple accounts to dodge the daily limit. Throttle and cache.
- **No-key fallback:** `public - v1` endpoint returns 500 records with no key. Sufficient for building and testing the ingest script.

### IMF PortWatch
- **What:** Daily transit calls and trade volume estimates for 28 maritime chokepoints, derived from satellite AIS signals on ~90,000 ships
- **Access:** Free, no key. Served via ArcGIS FeatureServer, also downloadable as CSV/GeoJSON
- **Endpoint pattern:** `services9.arcgis.com/weJ1QsnbMYJlCHdG`, layer `Daily_Chokepoints_Data`, filtered by `portid`
- **Pagination:** Standard ArcGIS `resultOffset` / `resultRecordCount`
- **Refresh:** Weekly, Tuesdays ~9 AM ET
- **No bulk endpoint:** iterate over chokepoint IDs

### Reference data
- **USGS Mineral Commodity Summaries / US Critical Minerals List** — grounds the rare earth basket selection
- **DOE Critical Materials Assessment** — same purpose
- **UN Stats HS correlation tables** — source for the concordance bridge
- **US DOJ/FTC Merger Guidelines** — source for HHI concentration thresholds. Cite the version and year used.

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

---

## 6. Known hard problems

**HS concordance.** Codes split, merge, and retire across revisions (1996, 2002, 2007, 2012, 2017, 2022). Solved with a bridge table held as data, not as SQL.

**Product-to-chokepoint routing.** PortWatch gives chokepoint volumes; Comtrade gives product flows. No source links them. A routing assumption matrix must be constructed, documented explicitly, and sensitivity-tested. This is a modelling assumption, not a measurement. State what it ignores: routing substitution, air freight, transshipment.

**Basket routing relevance.** Hormuz is primarily an oil and gas chokepoint and likely has little bearing on either basket. Both baskets route predominantly via the South China Sea and Malacca. Choose event studies based on which chokepoints the baskets actually transit.

---

## 7. Architecture decisions

**Carry `hs_version` as a column** through raw and staging. Every row knows its classification vintage.

**Bridge table as data**, at `data/reference/hs_bridge.csv`:
```
canonical_product_id, hs_version, hs6_code, notes
```
One canonical product maps to many HS codes across vintages.

**Marts group by `canonical_product_id`, never by raw HS code.** This is what makes backward extension cheap: add rows to the CSV, widen the year range, `dbt build`. Zero SQL changes.

**Never hardcode** classification vintage or year range in SQL.

**`data/raw/` is immutable.** Never edited in place. Reference data in `data/reference/` is committed; raw data is gitignored.

**Transformation logic lives in dbt**, not in pandas. Python is for ingest, scenario arithmetic, and charts SQL cannot make.

---

## 8. Stack

| Layer | Tool | Why |
|---|---|---|
| Ingest | Python: `comtradeapicall`, `requests`, `pandas`, `pyarrow` | Official client; ArcGIS needs plain requests |
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
trade-chokepoint-exposure/
├── PROJECT_BRIEF.md
├── CLAUDE.md               # gitignored
├── README.md
├── .gitignore
├── .env.example
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
│   ├── comtrade.py
│   ├── portwatch.py
│   └── reference.py
├── data/
│   ├── raw/                # gitignored, immutable
│   └── reference/          # committed: hs_bridge.csv, routing_matrix.csv, basket_definitions.csv
├── dbt/
│   ├── models/{staging,intermediate,marts}/
│   ├── tests/
│   └── dbt_project.yml
├── analysis/
├── viz/
└── .github/workflows/refresh.yml
```

**dbt layer rules:**
- `staging/` — one model per source table. Rename, cast, unpivot. No joins, no aggregation. Prefix `stg_`.
- `intermediate/` — joins and business logic. Not consumed directly. Prefix `int_`.
- `marts/` — what BI reads. Prefix `fct_` and `dim_`.

---

## 10. Core measures

**HHI (Herfindahl-Hirschman Index):** sum of squared partner import-value shares, per canonical product per year. Scale 0 to 10,000. Thresholds sourced from current DOJ/FTC Merger Guidelines, version cited in the data dictionary.

**Also report:** top supplier share, top-3 concentration, supplier count. HHI is analytically better; top supplier share is what a procurement person intuitively reads. Report both and explain why.

**Exposure score:** share of import value originating in regions routing through each chokepoint, per the routing matrix. Implemented as a SQL join, surfaced as a dashboard filter rather than a parametrized engine.

**Event study — candidates, not yet decided:**
- Suez / Bab el-Mandeb versus Cape of Good Hope, before and after Nov 2023 (clean substitution story; traffic visibly rerouted)
- Malacca — most relevant to both baskets, but watch the 2021 series break
- Hormuz — high news salience, but documented data quality issues and likely low relevance to these baskets

Decide after inspecting the data. Do not commit early.

---

## 11. Deliverables

**Must ship:**
- Working ingest for both sources, reproducible from cold start
- Postgres landing schema
- dbt project: staging, intermediate, marts, 12–15 tests, generated lineage docs
- HHI and exposure marts
- Routing assumption matrix, documented
- One event study
- Tableau Public dashboard at a live URL
- Excel scenario workbook (named parameter cells, data validation, two-variable Data Table, XLOOKUP, conditional formatting)
- All seven `/docs` artifacts
- README with screenshots and links

**Stretch:** Streamlit app; HS2012 backward extension.

**Later, separate weekends:** Snowflake port; Power BI report.

---

## 12. Framing for different audiences

The framework is product-agnostic. Baskets are rows in `dim_product`, not hardcoded logic. Say so in the README.

- **Semiconductor / hardware:** supplier concentration in the products they actually buy
- **Consulting:** unfamiliar domain, sourced data, defensible framework, documented assumptions, recommendation. Frame as a client engagement.
- **Tech:** lead with "concentration risk framework," not "trade data." HHI generalises to revenue concentration by customer, vendor concentration, marketplace seller concentration.
- **Financial services / risk:** counterparty and country risk, trade finance
- **Logistics and freight tech:** close to core business

Pitch commercially (corporate supply chain risk), not geopolitically. Geopolitical framing points at defense and government employers, most of which require US Person status.

---

## 13. Repo hygiene

- `CLAUDE.md` and `.claude/` in `.gitignore`
- No co-author trailers or "Generated with" footers in commit messages
- `.env` gitignored before any key is ever written to it
- Squash or reword early history before the repo goes public

---

## 14. Decision log

| Date | Decision | Rejected alternative | Reason |
|---|---|---|---|
| 2026-09-13 | US as sole reporter | US + EU27 comparison | Doubles data volume and concordance work for marginal analytical gain within a 5-day build |
| 2026-09-13 | Baskets: semis+SME, rare earths+magnets | Pharma APIs; substrates/advanced packaging | Semis match referral network and SEMICON West; rare earths give the most portable and legible concentration story |
| 2026-09-13 | HHI as primary concentration measure | Top-supplier share alone | Top share cannot distinguish one dominant supplier from two; HHI can. Both reported. |
| 2026-09-13 | Static exposure score, dashboard filter | Parametrized Python scenario engine | Same analytical payload, roughly one day cheaper to build |
| 2026-09-13 | HS2017 first, HS2012 as enhancement | Full 1996-present concordance | Working pipeline by Friday matters more than range; bridge-table design makes extension cheap |
| 2026-09-13 | Chokepoints only | Include 2,065-port dataset | Ports add volume without serving the stakeholder decision |
| 2026-09-13 | Defer Snowflake and Power BI | Build on them now | Neither improves the analysis; both cost setup time inside a 5-day window |

---

## 15. Open questions

- [ ] Verify all candidate HS6 codes against the live Comtrade code list
- [ ] Confirm latest available Comtrade year for US imports
- [ ] Inspect record counts by year to see classification breaks directly
- [ ] Decide event study after data inspection
- [ ] Pull current DOJ/FTC Merger Guidelines and record the HHI bands and guideline version
- [ ] Confirm which chokepoints the two baskets actually route through before building the routing matrix
