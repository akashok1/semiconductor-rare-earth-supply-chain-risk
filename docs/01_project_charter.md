# Project Charter: Import Concentration Risk

| Field | Value |
|---|---|
| Project name | Import Concentration Risk |
| Repository | `import-concentration-risk` |
| Document ID | `docs/01_project_charter.md` |
| Version | 1.1 |
| Status | Amended post-Verification, approved for build |
| Author | Akash A, Business Analyst |
| Date | 2026-09-18 |
| Supersedes | 1.0 (2026-09-14) |

**Version history**

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-09-14 | Approved for build | Akash A |
| 1.1 | 2026-09-18 | Amended to match Verification findings. Routing changed from assumed to computed. Census added as a third source. HS bridge promoted to first release requirement. Basket framing made asymmetric. Assumptions and risks rewritten around the weaknesses that remain rather than the ones removed | Akash A |

> Scope, stakeholder framing, and architecture decisions in this charter derive from `PROJECT_BRIEF.md`. Where the two disagree, `PROJECT_BRIEF.md` wins and this document gets a version bump. Where either disagrees with `docs/07_assumptions_limitations.md` on a matter of fact, the assumptions document wins, because it records what was measured.

---

## 1. Purpose

This charter authorises the build, fixes its boundaries, and names the single decision it exists to support. It is written so that any requirement, model, test, or chart in the repository can be challenged with one question: which objective in section 4 does this serve?

## 2. Background and business problem

A mid-size US electronics manufacturer buys semiconductor components, semiconductor manufacturing equipment, rare earth inputs, and permanent magnets. Its supply chain risk committee reviews supplier arrangements once a year, ahead of contract renewals.

Two risks currently sit outside the committee's visibility.

The first is supplier concentration. Purchasing data tells the committee who it buys from. It does not tell the committee how many credible suppliers exist in the world for a given input, or whether the global supply of that input sits in one country. A supplier that looks diversified at the invoice level can be single sourced two tiers up.

The second is physical routing risk. Concentration in a distant country only matters if the goods have to move, and goods move through a small number of maritime chokepoints. The Red Sea disruption from late 2023 showed that a chokepoint closure reprices and reroutes freight within weeks. The committee has no view of which of its inputs are exposed to which chokepoint.

Neither risk is measured today. Committee discussion is anecdotal and driven by whatever was in the news that quarter.

Verification changed the shape of the second risk. The two baskets do not move the same way. Semiconductors and semiconductor manufacturing equipment travel 70 to 98 percent by air, with 854231 moving 0.8 percent by vessel, $1.59B against $196.73B total. Rare earths and permanent magnets travel 57 to 75 percent by containerized vessel. Physical routing risk is therefore a live concern for one basket and close to irrelevant for the other. That asymmetry is a finding this project reports, not a gap it apologises for, and it is the reason the two baskets are framed differently in section 5.

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
| OBJ-2 | Quantify maritime chokepoint exposure for every in scope input, and state honestly how much of each basket's physical flow that figure covers | Exposure score produced per canonical product per chokepoint, computed from measured mode shares, measured coast shares, and computed route crossings. Every score traceable to a committed reference file. Vessel share coverage stated beside every exposure figure | `routing_matrix.csv`, `mode_shares.csv`, `port_entry_shares.csv`, `fct_exposure` |
| OBJ-3 | Show how concentration and exposure have changed | Continuous series 2018 to 2025 across both classification vintages, with the bridge table resolving every code that split or retired, and comparability breaks flagged rather than silently smoothed | `hs_bridge.csv`, dashboard trend view, `vintage_break_year` and `code_status` flags |
| OBJ-4 | Make the numbers trustworthy enough to argue with | Every published data quality anomaly encoded as a dbt test; the build fails when an excluded date appears in the clean mart | `dbt test` result, 12 to 15 tests minimum |
| OBJ-5 | Make the analysis reproducible from cold start | A reader with the repo, Docker, and the two API keys reproduces the marts using documented commands only | `README.md` runbook, verified once on a clean clone |
| OBJ-6 | Deliver the result in a form the committee can use without a licence | Public Tableau URL, plus an Excel scenario workbook that runs without a BI tool | Live dashboard link, workbook in repo |

Success criteria are deliberately mechanical. None of them is "stakeholder is satisfied", because the stakeholder is fictional and that criterion would be unfalsifiable.

## 5. Scope

| Dimension | In scope | Out of scope |
|---|---|---|
| Reporter | United States | All other importers |
| Partner | All partners | None |
| Products | Two baskets, 22 verified HS6 codes in HS2017, resolving to 26 codes in HS2022 | All other HS codes |
| Classification | HS2017 (H5) for 2018 to 2021 and HS2022 (H6) for 2022 onward. Both required in the first release | Vintages before 2017 |
| Years | 2018 to 2025 | Partial year 2026 |
| Maritime data | All 28 IMF PortWatch chokepoints ingested. Crossings computed, not assumed | The 2,065 port dataset |
| Flow direction | Imports | Exports and re-exports |
| Analysis depth | One event study | Multiple event studies |

The 22 codes are the verified set, recorded in `data/reference/basket_selection.csv` with an include or exclude decision per code. Version 1.0 estimated roughly 35 codes. That estimate was arithmetic error rather than a filter: the 8541, 8542, 8486 and 2846 families are exhaustively enumerated at HS6 and total 22 with 280530 and 850511. No candidate code was dropped for low value.

**Basket 1: semiconductors and semiconductor manufacturing equipment.** HS 8541, 8542 and 8486 families, 18 codes. This basket carries the concentration analysis. Its exposure figures are computed and published, but they cover the minority of physical flow that moves by sea, and every exposure figure for this basket states its vessel share coverage. An exposure score near zero here means the goods fly, not that the model failed.

**Basket 2: rare earths and permanent magnets.** HS 280530, 284610, 284690, 850511, 4 codes. This basket carries both the concentration and the exposure analysis, since 57 to 75 percent of its value moves by containerized vessel.

**Explicitly excluded, with reasons**

- Tier two and tier three supply visibility. No public dataset supports it. Comtrade measures shipments between countries, not corporate ownership.
- Air freight routing. Census measures the air share per code, so air value is removed from the exposure denominator rather than routed. No public source gives air corridors or transfer hubs at commodity level.
- Land border trade routing. Mexico and Canada imports are 95.5 and 74.8 percent land respectively. Land value has no maritime chokepoint exposure and is removed from the exposure denominator. It remains in every concentration measure.
- Transshipment and carrier routing substitution. Not separable in the source data. Recorded as assumption A-3.
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
| D-1 | Ingest for UN Comtrade, US Census, and IMF PortWatch | Runs from cold start, fails loudly on auth failure, never writes an empty file silently |
| D-2 | PostgreSQL landing schema | Raw tables carry `hs_version` and an ingest timestamp |
| D-3 | dbt project, staging to intermediate to marts | `dbt build` passes; lineage docs generate |
| D-4 | 12 to 15 dbt tests | Includes one test per published PortWatch anomaly, and one vintage break continuity test |
| D-5 | Concentration mart | HHI, top share, top three share, supplier count |
| D-6 | Exposure mart and computed routing matrix | `routing_matrix.csv` committed with one row per origin, destination and chokepoint combination including non-crossings, carrying the measured distance and the threshold used. Exposure mart joins it to measured mode and coast shares |
| D-7 | One event study | Written up with what it shows and what it cannot show |
| D-8 | Sensitivity test of the 200km proximity threshold | Exposure ranking reported at 50, 100, 200 and 300km, with any rank change named |
| D-9 | Tableau Public dashboard | Live URL, loads without a login |
| D-10 | Excel scenario workbook | Named parameter cells, data validation, two variable data table, XLOOKUP, conditional formatting |
| D-11 | Seven documents in `/docs` | Charter, BRD, FRD, data dictionary, traceability matrix, UAT test plan, assumptions and limitations |
| D-12 | README with screenshots and links | A reader understands the finding without cloning |

**Stretch:** Streamlit scenario app; HS2012 backward extension.

**Deferred, not cancelled:** Snowflake port; Power BI report.

## 8. Milestones

| Phase | Exit condition |
|---|---|
| Verification | **Complete, 2026-09-17.** Comtrade key working, 22 HS6 codes verified against the live code list, latest year confirmed as 2025, classification break located at 2021/2022, PortWatch pagination working, Census mode and port data verified, route crossings computed. Findings recorded in `docs/07_assumptions_limitations.md` |
| Ingest | Raw tables landed in Postgres, staging models built, `hs_bridge.csv` populated, first tests passing |
| Measures | Concentration mart complete, routing matrix committed and documented, exposure mart complete |
| Analysis and BI | Event study chosen and run, sensitivity test run, Tableau dashboard built, Excel workbook built |
| Documentation | FRD, data dictionary, traceability matrix, UAT test plan written; assumptions and limitations kept current; GitHub Actions workflow committed; README finished; history squashed; repo made public |

The Verification phase gated everything and its findings moved the scope. This document is the amendment. Where a section of version 1.0 asserted something Verification disproved, the assertion has been replaced and the disproof recorded, not deleted. Hypotheses stated in advance and then falsified are kept, since stating them in advance was the point.

## 9. Assumptions

Assumptions A-1 through A-6 in version 1.0 were pre-Verification. Four were tested and replaced by measurement, recorded in `docs/07_assumptions_limitations.md` section 3. What remains cannot be tested with public data. Each is stated wherever the affected number appears.

| ID | Assumption | Why it cannot be tested | If it proves false |
|---|---|---|---|
| A-1 | Country of origin approximates production origin | Comtrade records last substantial transformation, not corporate or upstream structure | Concentration is understated. Malaysia at 33 percent of integrated circuits is assembly and test of wafers fabricated elsewhere |
| A-2 | Comtrade partner code 490, "Other Asia, nes", is Taiwan | Taiwan is not a UN member and is reported as a residual category | Minor, but material given Taiwan Strait ranks among the crossed chokepoints. A convention, not a measurement |
| A-3 | The shortest sea route approximates the route actually sailed | No public dataset links a shipment to a route. The searoute authors state the tool produces realistic looking routes rather than navigational ones | Exposure attributed to the wrong chokepoint where carriers deviate for cost, weather, congestion or alliance routing. **This is now the weakest assumption in the build** |
| A-4 | One representative port stands for a whole country's exports | Comtrade gives partner country, not port of loading | Crossings misattributed for countries with coasts on different seas. China is routed from Shanghai, so southern Chinese exports may route differently |
| A-5 | Import value share is a reasonable proxy for physical dependency | No public source gives unit volumes consistently across products | Products with volatile prices show concentration shifts that reflect price, not supply. Net weight reported alongside value as a partial check |
| A-6 | Chokepoint transit counts reflect route activity | Documented AIS signal loss and transponder suppression in some regions | Affected chokepoints flagged rather than used as reliable volumes |
| A-7 | A 200km radius around a chokepoint's published point coordinate captures transit of that chokepoint | PortWatch publishes each chokepoint as a single point, but a chokepoint is an area. The Strait of Malacca runs roughly 800km, so exact intersection would be meaningless and some radius is required | Too tight drops real crossings, too loose invents them. **This is the only free parameter left in the routing computation, and D-8 exists for it** |
| A-8 | Comtrade free tier access remains available at 500 calls per day | Operational, not analytical | Fall back to the keyless endpoint at 500 records and narrow the year range. All responses are cached, so a dead key blocks new pulls, not transformation |

A per-chokepoint threshold scaled to each strait's real width was considered and rejected. It would replace one stated parameter with 28 hand-assigned ones, reintroducing exactly the subjective input that computing the routing matrix removed.

## 10. Constraints

- Five day build window. Anything that does not serve section 4 gets cut rather than deferred quietly.
- MacBook M2 with 8GB RAM. Heavy joins run in Postgres, not pandas. Docker, a large pandas session, and a heavy browser do not run at once.
- Free tiers only. Comtrade free tier, Census free tier, Tableau Public, GitHub Actions free minutes.
- Two API keys required, Comtrade and Census, both free tier, both in `.env` and never committed.
- Published concordance tables are not authoritative. The UN Stats HS2022 to HS2017 correlation table misattributes the successors of 854150 and required empirical resolution. Any concordance the build relies on is validated against trade value before use.
- Tableau Public makes the workbook and its data public. No confidential input can enter the project, which is fine because every source is public.
- Single analyst. No peer review, so tests and documentation carry the review load.

## 11. Dependencies

| Dependency | Type | Risk if it fails |
|---|---|---|
| UN Comtrade API | External, keyed | Blocks concentration analysis entirely |
| US Census international trade API | External, keyed | Blocks the mode and coast shares, which blocks exposure entirely. Comtrade reports TOTAL MOT only for the US, so there is no substitute |
| IMF PortWatch ArcGIS FeatureServer | External, keyless | Blocks chokepoint coordinates and the event study. No alternative free AIS source |
| searoute and the Eurostat ocean network | Local package | Blocks route computation. No API dependency, so failure means a broken environment, not a dead service |
| UN/LOCODE, OSM-filled republication | Reference, cached | Blocks port coordinate resolution. Official UN/LOCODE lacks coordinates for several ports including Kaohsiung |
| UN Stats HS correlation tables | Reference, cached | Blocks the bridge table, which now blocks the 2022 onward series. Promoted from enhancement to critical path |
| Census Schedule D port and district codes | Reference, cached | Blocks coast classification. Classification by port name puts land crossings in Unclassified |
| DOJ and FTC Merger Guidelines | Reference | Blocks HHI threshold interpretation, not computation |
| USGS and DOE critical materials lists | Reference | Weakens basket justification |
| Docker and PostgreSQL local | Local | Blocks the whole pipeline |

## 12. Risks

| ID | Risk | Likelihood | Impact | Response |
|---|---|---|---|---|
| R-1 | Comtrade free tier key is regenerated or deactivated mid build | Medium | High | Ingest fails loudly on 401. Portal login every two weeks. Raw data cached locally so a dead key does not block transformation |
| R-2 | The routing computation is judged unrealistic by a reviewer with logistics experience | Medium | High | Routing is computed rather than assigned, so the argument moves from "why these weights" to "why shortest route" and "why 200km". A-3 and A-7 state both plainly. D-8 tests the threshold. What remains unanswerable is carrier behaviour, and the charter says so rather than defending it |
| R-3 | HS concordance breaks the time series | Medium | High | Raised from Medium impact after Verification. `hs_version` carried through every layer, bridge table held as data, `code_status` distinguishes a retired code from a data gap. Every concordance validated against trade value continuity across the vintage break before use |
| R-4 | PortWatch series breaks read as real growth | Medium | Medium | Known breaks flagged in the mart and annotated on the dashboard |
| R-5 | Scope creep into ports, more baskets, or more reporters | High | Medium | Scope table in section 5 is the test. Additions require a decision log entry |
| R-6 | Documentation volume outpaces analytical substance | Medium | High | The event study and sensitivity test ship before any document other than this charter, the BRD, and the assumptions record |
| R-7 | Five day window slips | High | Low | Priority order on slip: D-1 to D-6, then D-9, then D-11, then D-7 and D-8, then D-10 |
| R-8 | An exposure figure near zero for the semiconductor basket is read as a broken model rather than as air freight | Medium | Medium | Vessel share coverage published beside every exposure figure. Basket asymmetry stated in section 5, in the BRD, and on the dashboard landing view |

R-2 is still the one that decides how this project is received, but its surface has narrowed. Concentration numbers are computed from measured trade values and are hard to dispute. Routing is now computed rather than assigned, which removes the "why these weights" argument. What a logistics reviewer can still challenge is whether a shortest sea route resembles a sailed route at all, and whether a single point coordinate plus a radius represents a strait. Those are A-3 and A-7, and neither is defended, only stated.

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
| Analyst and owner | Akash A | 2026-09-18 | Amended and approved |
| Sponsor (simulated) | Supply chain risk committee | 2026-09-18 | Approved for build |

> Simulated sign off. The stakeholder is a constructed scenario used to keep scope disciplined. This is stated plainly here so that nothing in the repository misrepresents itself as client work.
