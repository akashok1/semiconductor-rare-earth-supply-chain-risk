# Project Charter: Trade Chokepoint Exposure

| Field | Value |
|---|---|
| Project name | Trade Chokepoint Exposure |
| Repository | `trade-chokepoint-exposure` |
| Document ID | `docs/01_project_charter.md` |
| Version | 1.0 |
| Status | Approved for build |
| Author | Akash A, Business Analyst |
| Date | 2026-09-14 |
| Supersedes | None |

> Scope, stakeholder framing, and architecture decisions in this charter derive from `PROJECT_BRIEF.md`. Where the two disagree, `PROJECT_BRIEF.md` wins and this document gets a version bump.

---

## 1. Purpose

This charter authorises the build, fixes its boundaries, and names the single decision it exists to support. It is written so that any requirement, model, test, or chart in the repository can be challenged with one question: which objective in section 4 does this serve?

## 2. Background and business problem

A mid-size US electronics manufacturer buys semiconductor components, semiconductor manufacturing equipment, rare earth inputs, and permanent magnets. Its supply chain risk committee reviews supplier arrangements once a year, ahead of contract renewals.

Two risks currently sit outside the committee's visibility.

The first is supplier concentration. Purchasing data tells the committee who it buys from. It does not tell the committee how many credible suppliers exist in the world for a given input, or whether the global supply of that input sits in one country. A supplier that looks diversified at the invoice level can be single sourced two tiers up.

The second is physical routing risk. Concentration in a distant country only matters if the goods have to move, and goods move through a small number of maritime chokepoints. The Red Sea disruption from late 2023 showed that a chokepoint closure reprices and reroutes freight within weeks. The committee has no view of which of its inputs are exposed to which chokepoint.

Neither risk is measured today. Committee discussion is anecdotal and driven by whatever was in the news that quarter.

## 3. Decision supported

**Ahead of annual supplier contract renewals, where should the committee qualify a second supplier, and where should it hold buffer inventory?**

Second sourcing and buffer inventory are both expensive. The committee cannot do either everywhere. It needs a defensible ranking of inputs by risk, and it needs to see the assumptions behind that ranking so it can argue with them.

Three questions follow from the decision:

1. Which inputs depend on a small number of foreign suppliers?
2. Which of those dependencies route through a maritime chokepoint?
3. How has that exposure moved over time?

## 4. Objectives and success criteria

| ID | Objective | Success criterion | Measured by |
|---|---|---|---|
| OBJ-1 | Quantify supplier concentration for every in scope input | HHI, top supplier share, top three share, and supplier count produced for 100% of canonical products for every year in range | `fct_concentration` row count reconciles to product count multiplied by year count |
| OBJ-2 | Quantify maritime chokepoint exposure for every in scope input | Exposure score produced per canonical product per chokepoint, with the routing assumption behind every score readable from a committed reference file | `routing_matrix.csv` plus `fct_exposure` |
| OBJ-3 | Show how concentration and exposure have changed | Full series available from 2018 to the latest published year with classification breaks flagged rather than silently smoothed | Dashboard trend view, series break flags |
| OBJ-4 | Make the numbers trustworthy enough to argue with | Every published data quality anomaly encoded as a dbt test; the build fails when an excluded date appears in the clean mart | `dbt test` result, 12 to 15 tests minimum |
| OBJ-5 | Make the analysis reproducible from cold start | A reader with the repo, Docker, and a Comtrade key reproduces the marts using documented commands only | `README.md` runbook, verified once on a clean clone |
| OBJ-6 | Deliver the result in a form the committee can use without a licence | Public Tableau URL, plus an Excel scenario workbook that runs without a BI tool | Live dashboard link, workbook in repo |

Success criteria are deliberately mechanical. None of them is "stakeholder is satisfied", because the stakeholder is fictional and that criterion would be unfalsifiable.

## 5. Scope

| Dimension | In scope | Out of scope |
|---|---|---|
| Reporter | United States | All other importers |
| Partner | All partners | None |
| Products | Two baskets, roughly 35 HS6 codes | All other HS codes |
| Classification | HS2017 (H5) first, HS2012 (H4) as an enhancement | Vintages before 2012 |
| Years | 2018 to latest available | Before 2018 in the first release |
| Maritime data | 28 IMF PortWatch chokepoints | The 2,065 port dataset |
| Flow direction | Imports | Exports and re-exports |
| Analysis depth | One event study | Multiple event studies |

**Baskets**

1. Semiconductors and semiconductor manufacturing equipment: HS 8541, 8542, 8486 families.
2. Rare earths and permanent magnets: HS 2805.30, the 2846 family, 8505.11.

HS codes listed above are candidates. Every one is verified against the live Comtrade code list on Day 1 before it enters `dim_product`.

**Explicitly excluded, with reasons**

- Tier two and tier three supply visibility. No public dataset supports it. Comtrade measures shipments between countries, not corporate ownership.
- Air freight and transshipment routing. Not separable in the source data. Recorded as a limitation, not modelled.
- Price and cost modelling. The decision is about second sourcing and buffer stock, not landed cost.
- Forecasting. The model measures exposure as it stands and as it has moved, not where it goes next.

## 6. Stakeholders

| Stakeholder | Role in the project | Interest |
|---|---|---|
| Supply chain risk committee (primary) | Decision maker, accepts the deliverable | Ranking of inputs by concentration and exposure, with visible assumptions |
| Procurement lead | Consumer of output | Which categories need a second qualified supplier before renewal |
| Operations and inventory planning | Consumer of output | Where buffer stock is justified and how much |
| Finance | Reviewer | Cost of holding buffer inventory against the risk avoided |
| Business Analyst (Akash A) | Analysis, build, documentation | Delivery of all objectives in section 4 |

RACI for the build itself is trivial, since one person executes every task. It is recorded here only so the document does not pretend to a team that does not exist.

## 7. Deliverables

**Must ship**

| ID | Deliverable | Acceptance |
|---|---|---|
| D-1 | Ingest for UN Comtrade and IMF PortWatch | Runs from cold start, fails loudly on auth failure, never writes an empty file silently |
| D-2 | PostgreSQL landing schema | Raw tables carry `hs_version` and an ingest timestamp |
| D-3 | dbt project, staging to intermediate to marts | `dbt build` passes; lineage docs generate |
| D-4 | 12 to 15 dbt tests | Includes one test per published PortWatch anomaly |
| D-5 | Concentration mart | HHI, top share, top three share, supplier count |
| D-6 | Exposure mart and routing assumption matrix | Matrix committed as data with a stated basis per row |
| D-7 | One event study | Written up with what it shows and what it cannot show |
| D-8 | Sensitivity test of the routing assumptions | Result changes reported when routing weights are varied |
| D-9 | Tableau Public dashboard | Live URL, loads without a login |
| D-10 | Excel scenario workbook | Named parameter cells, data validation, two variable data table, XLOOKUP, conditional formatting |
| D-11 | Seven documents in `/docs` | Charter, BRD, FRD, data dictionary, traceability matrix, UAT test plan, assumptions and limitations |
| D-12 | README with screenshots and links | A reader understands the finding without cloning |

**Stretch:** Streamlit scenario app; HS2012 backward extension.

**Deferred, not cancelled:** Snowflake port; Power BI report.

## 8. Milestones

| Day | Milestone | Exit condition |
|---|---|---|
| Day 1 | Data reality check | Comtrade key works, every HS6 code verified against the live code list, latest available year confirmed, record counts inspected by year, PortWatch layer paginating correctly |
| Day 2 | Pipeline standing | Raw tables landed in Postgres, staging models built, `hs_bridge.csv` populated, first tests passing |
| Day 3 | Measures built | Concentration mart complete, routing matrix drafted and documented, exposure mart complete |
| Day 4 | Analysis and BI | Event study chosen and run, sensitivity test run, Tableau dashboard built, Excel workbook built |
| Day 5 | Documentation and release | FRD, data dictionary, traceability matrix, UAT test plan, assumptions and limitations written; GitHub Actions workflow committed; README finished; history squashed; repo made public |

Day 1 gates everything. If the HS codes or the year range come back different from the assumptions in section 5, the scope table is amended before any model is written, not after.

## 9. Assumptions

| ID | Assumption | If it proves false |
|---|---|---|
| A-1 | Comtrade free tier access remains available at 500 calls per day | Fall back to the keyless `public - v1` endpoint at 500 records and narrow the year range |
| A-2 | The candidate HS6 codes exist in HS2017 and carry meaningful US import value | Replace codes on Day 1 and amend the scope table |
| A-3 | Bilateral import value is an acceptable proxy for supply dependency | Stated as a limitation; no alternative public source exists |
| A-4 | Country of origin in Comtrade approximates the true production origin | Recorded as a limitation. Transshipment and rules of origin distort this and the distortion is not measurable here |
| A-5 | Chokepoint transit volumes from PortWatch are a reasonable proxy for route activity | Flagged chokepoints with known signal loss are caveated, not silently used |
| A-6 | Routing weights assigned by region are directionally correct | This is the weakest assumption in the build. It is why D-8 exists |

## 10. Constraints

- Five day build window. Anything that does not serve section 4 gets cut rather than deferred quietly.
- MacBook M2 with 8GB RAM. Heavy joins run in Postgres, not pandas. Docker, a large pandas session, and a heavy browser do not run at once.
- Free tiers only. Comtrade free tier, Tableau Public, GitHub Actions free minutes.
- Tableau Public makes the workbook and its data public. No confidential input can enter the project, which is fine because every source is public.
- Single analyst. No peer review, so tests and documentation carry the review load.

## 11. Dependencies

| Dependency | Type | Risk if it fails |
|---|---|---|
| UN Comtrade API | External, keyed | Blocks concentration analysis entirely |
| IMF PortWatch ArcGIS FeatureServer | External, keyless | Blocks exposure analysis; no alternative free AIS source |
| UN Stats HS correlation tables | Reference | Blocks backward extension only |
| DOJ and FTC Merger Guidelines | Reference | Blocks HHI threshold interpretation, not computation |
| USGS and DOE critical materials lists | Reference | Weakens basket justification |
| Docker and PostgreSQL local | Local | Blocks the whole pipeline |

## 12. Risks

| ID | Risk | Likelihood | Impact | Response |
|---|---|---|---|---|
| R-1 | Comtrade free tier key is regenerated or deactivated mid build | Medium | High | Ingest fails loudly on 401. Portal login every two weeks. Raw data cached locally so a dead key does not block transformation |
| R-2 | Routing matrix is judged arbitrary by a reviewer | High | High | Every weight carries a stated basis. Sensitivity test is a must ship, not a stretch. The matrix is presented as an assumption, never as a measurement |
| R-3 | HS concordance breaks the time series | Medium | Medium | `hs_version` carried through every layer. Bridge table held as data. Record counts inspected by year on Day 1 to find breaks directly |
| R-4 | PortWatch series breaks read as real growth | Medium | Medium | Known breaks flagged in the mart and annotated on the dashboard |
| R-5 | Scope creep into ports, more baskets, or more reporters | High | Medium | Scope table in section 5 is the test. Additions require a decision log entry |
| R-6 | Documentation volume outpaces analytical substance | Medium | High | The event study and sensitivity test ship before any document other than this charter and the BRD |
| R-7 | Five day window slips | High | Low | Priority order on slip: D-1 to D-6, then D-9, then D-11, then D-7 and D-8, then D-10 |

R-2 is the one that decides how this project is received. Concentration numbers are computed from measured trade values and are hard to dispute. Exposure numbers rest on judgement about which goods travel which way, and a reviewer who has worked in logistics will go straight at it.

## 13. Definition of done

The project is done when all of the following hold:

1. `dbt build` passes from a clean clone against a freshly ingested database.
2. Every objective in section 4 has its stated evidence present in the repository.
3. The Tableau URL loads for an anonymous visitor.
4. The seven documents in `/docs` are internally consistent, meaning every requirement in the BRD appears in the traceability matrix and resolves to a shipped artefact or an explicit deferral.
5. No secret has ever been committed. Verified by scanning the full history before the repository goes public.
6. `README.md` states the finding, the method, the assumptions, and what the analysis cannot support.

## 14. Sign off

| Role | Name | Date | Decision |
|---|---|---|---|
| Analyst and owner | Akash A | 2026-09-14 | Approved |
| Sponsor (simulated) | Supply chain risk committee | 2026-09-14 | Approved for build |

> Simulated sign off. The stakeholder is a constructed scenario used to keep scope disciplined. This is stated plainly here so that nothing in the repository misrepresents itself as client work.
