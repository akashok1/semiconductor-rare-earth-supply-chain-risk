# Business Requirements Document: Import Concentration Risk

| Field | Value |
|---|---|
| Project name | Import Concentration Risk |
| Document ID | `docs/02_brd.md` |
| Version | 1.0 |
| Status | Baselined for build |
| Author | Akash A, Business Analyst |
| Date | 2026-09-14 |
| Related documents | `docs/01_project_charter.md`, `docs/03_frd.md`, `docs/05_traceability_matrix.md` |

**Version history**

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-09-13 | Draft from project brief | Akash A |
| 1.0 | 2026-09-14 | Baselined ahead of the Verification phase | Akash A |

> This document states **what the business needs and why**. It does not state how the solution is built. Models, tests, endpoints, and schemas live in the FRD. Every requirement here carries an ID that the traceability matrix uses to connect a business need to a functional specification, a test case, and a shipped artefact.

---

## 1. Executive summary

The supply chain risk committee of a mid-size US electronics manufacturer must decide, before annual contract renewals, where to qualify a second supplier and where to hold buffer inventory. It currently has no measure of how concentrated the global supply of its inputs is, and no measure of how exposed that supply is to a maritime chokepoint disruption.

This project delivers a measured concentration and exposure model for two product baskets, built on public trade and maritime data, surfaced in a dashboard and a scenario workbook, with every assumption documented and tested.

The distinction that runs through this document: concentration is **measured**, exposure is **modelled**. Requirements are written so a reader can always tell which is which.

## 2. Business context

The committee buys two categories where supply is known anecdotally to be geographically narrow: semiconductors with their manufacturing equipment, and rare earths with permanent magnets. Both categories moved sharply in the trade policy environment of the last several years. Both travel by sea, predominantly through the South China Sea and the Strait of Malacca.

The committee's existing view is limited to its own purchase orders. Purchase orders show the immediate vendor, not the upstream production base. A contract with a diversified distributor can sit on top of a single country of origin.

## 3. Current state

| Aspect | Current state | Consequence |
|---|---|---|
| Concentration visibility | Vendor level only, from internal purchasing records | A single origin country behind multiple vendors is invisible |
| Routing visibility | None | Chokepoint risk is discussed only after it appears in the news |
| Trend visibility | None | Committee cannot distinguish a worsening dependency from a stable one |
| Basis of discussion | Anecdote and recent headlines | Second sourcing spend follows salience, not exposure |
| Repeatability | Ad hoc analyst pulls | Last year's numbers cannot be reproduced or compared |

## 4. Future state

The committee opens a dashboard before the renewal cycle and, for every input in scope, reads: how concentrated global supply is, how that has moved since 2018, which chokepoints the supply routes through, and how much of the exposure number depends on a routing judgement rather than a measurement. The underlying pipeline refreshes weekly without manual work, and any number on screen can be traced to a source file and a transformation.

## 5. Business objectives

| ID | Objective | Measure of success |
|---|---|---|
| BO-1 | Replace anecdotal concentration discussion with a measured index | Concentration metrics available for 100% of in scope products and years |
| BO-2 | Make maritime routing risk explicit and arguable | Exposure score per product per chokepoint, with every routing weight documented and its sensitivity tested |
| BO-3 | Enable comparison over time | Continuous series from 2018 to latest, with classification and sensor breaks flagged |
| BO-4 | Make outputs trustworthy | All published source data anomalies encoded as automated tests that fail the build |
| BO-5 | Make outputs usable without specialist tooling | Public dashboard plus an offline scenario workbook |
| BO-6 | Make the analysis repeatable next year | Reproducible from cold start using documented commands, refreshed on a schedule |

## 6. Stakeholder needs

| ID | Stakeholder | Need | Traces to |
|---|---|---|---|
| SN-1 | Risk committee | Rank inputs by dependency risk | BO-1, BO-3 |
| SN-2 | Risk committee | Understand which dependencies are physically exposed | BO-2 |
| SN-3 | Procurement lead | Identify categories to second source before renewal | BO-1, BO-2 |
| SN-4 | Operations planning | Identify where buffer stock is justified | BO-2 |
| SN-5 | Finance | Challenge the basis of any recommendation | BO-2, BO-4 |
| SN-6 | All | Read the output without a BI licence | BO-5 |

SN-5 is the reason this document distinguishes measurement from assumption everywhere. A recommendation that cannot be challenged will not be funded.

## 7. Scope summary

In scope and out of scope are fixed in section 5 of the project charter and are not restated here. Requirements below apply only within that boundary. A requirement that needs a scope change carries a note saying so.

## 8. Business requirements

Priority uses MoSCoW. **M** must have for this release, **S** should have, **C** could have, **W** will not have this time.

### 8.1 Supplier concentration

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-01 | The solution shall measure supplier concentration for each product in each year using the Herfindahl-Hirschman Index, computed on partner shares of US import value | M | HHI distinguishes one dominant supplier from two comparable ones; a top share figure cannot | HHI present for every product and year combination in range; values fall between 0 and 10,000; HHI reconciles to a manual calculation for one sampled product and year | BO-1, SN-1 |
| BR-02 | The solution shall report top supplier share, top three supplier share, and supplier count alongside HHI | M | Procurement reads a share figure intuitively; HHI needs interpretation. Both are reported and the difference explained | All four measures present for every product and year; the data dictionary explains why both families are shown | BO-1, SN-3 |
| BR-03 | The solution shall identify the top supplier country for each product and year | M | The decision is country specific, not just concentration specific | Named partner country present for every product and year | BO-1, SN-3 |
| BR-04 | The solution shall classify concentration against published thresholds, citing the guideline source and version used | M | A number without a threshold gives the committee no action trigger | Threshold bands and the guideline version recorded in the data dictionary and shown on the dashboard | BO-1, SN-5 |
| BR-05 | The solution shall group measures by a canonical product identifier rather than by raw commodity code | M | Codes split, merge, and retire across classification vintages; grouping by raw code silently breaks the series | Every mart aggregates on canonical product; no mart groups on a raw HS code | BO-3 |
| BR-06 | The solution shall report concentration separately for raw rare earth inputs and for downstream permanent magnets | S | The interesting question is whether concentration worsens downstream. It must be measured, not assumed | Both sub groups appear as distinct canonical products and are separately readable on the dashboard | BO-1, SN-1 |

### 8.2 Chokepoint exposure

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-07 | The solution shall produce an exposure score for each product against each in scope maritime chokepoint | M | The committee needs to connect a dependency to a physical route | Score present for every product and chokepoint pair in scope | BO-2, SN-2 |
| BR-08 | The solution shall base exposure on a documented routing assumption matrix held as committed reference data, not embedded in code | M | The assumption is the most contestable part of the analysis and must be inspectable and editable without touching logic | `routing_matrix.csv` in the repository, one row per origin region and chokepoint, each row carrying a stated basis | BO-2, SN-5 |
| BR-09 | The solution shall state explicitly that exposure is a modelled estimate, naming what it ignores, including routing substitution, air freight, and transshipment | M | Presenting a modelled figure as a measured one destroys the credibility of the measured figures next to it | Statement present on the dashboard, in the README, and in the assumptions and limitations document | BO-2, SN-5 |
| BR-10 | The solution shall report how much the exposure ranking changes when routing weights are varied | M | A ranking that flips under a small change in assumptions is not a basis for spending money | Sensitivity result published showing the ranking under at least two alternative weightings | BO-2, SN-5 |
| BR-11 | The solution shall allow the committee to view exposure filtered to a single chokepoint | S | The committee's questions arrive chokepoint first when an event is in the news | Chokepoint filter available on the dashboard | BO-2, SN-2 |

### 8.3 Trend and event history

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-12 | The solution shall present concentration for each product as a continuous annual series from 2018 to the latest available year | M | A single year cannot distinguish a worsening dependency from a stable one | Series renders with no missing years; missing source years are labelled as missing, never interpolated | BO-3, SN-1 |
| BR-13 | The solution shall flag any year where a classification change affects comparability | M | A concordance artefact that looks like a real shift will be read as one | Affected years visibly flagged in the mart and annotated on the dashboard | BO-3, BO-4 |
| BR-14 | The solution shall include one event study examining chokepoint traffic before and after a real disruption | M | Demonstrates that the maritime data responds to real events, which is what makes the exposure model plausible at all | One event study published with the disruption named, the comparison window stated, and the limits of the inference stated | BO-2, BO-3 |
| BR-15 | The solution shall extend the concentration series to earlier classification vintages | C | Longer history strengthens trend reading but does not change this year's decision | Additional years present with vintage labelled | BO-3 |

### 8.4 Data trust and quality

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-16 | The solution shall exclude known source blackout dates from any published measure | M | Publishing a zero that is actually a sensor outage understates traffic and misleads | Blackout dates absent from the clean mart; an automated test asserts zero rows on those dates and fails the build otherwise | BO-4, SN-5 |
| BR-17 | The solution shall flag chokepoints and periods affected by signal interference or transponder suppression rather than presenting the volumes as reliable | M | Affected volumes understate real traffic by an unknown amount | Flag column present and surfaced wherever an affected chokepoint appears on the dashboard | BO-4 |
| BR-18 | The solution shall flag documented sensor coverage changes as series breaks and not present them as growth | M | A coverage expansion looks exactly like a demand increase in the raw series | Break flag present for the affected chokepoints and periods; dashboard annotation visible | BO-3, BO-4 |
| BR-19 | The solution shall pin the data version wherever a source has revised a chokepoint definition or boundary | M | Comparing across a boundary revision compares two different things | Data version recorded in the data dictionary; affected series labelled as not comparable across the revision | BO-4 |
| BR-20 | The solution shall fail loudly and stop when a source refuses access, rather than writing an empty or partial file | M | A silent empty ingest produces a clean looking dashboard built on nothing, which is the worst possible failure mode | Ingest raises on an authentication or authorisation failure; no output file is written; failure is visible in the run log | BO-4, BO-6 |
| BR-21 | The solution shall record, for every published measure, which source and which transformation produced it | M | Finance cannot challenge a number it cannot trace | Lineage documentation generated and published; data dictionary covers every mart column | BO-4, SN-5 |

### 8.5 Delivery and usability

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-22 | The solution shall deliver findings through an interactive dashboard reachable at a public URL without a login | M | Committee members and finance do not hold BI licences | URL loads for an anonymous visitor and renders all required views | BO-5, SN-6 |
| BR-23 | The solution shall provide a spreadsheet scenario workbook allowing a user to vary key parameters and see the effect | M | The committee's own modelling happens in spreadsheets; a leave behind gets used, a dashboard gets looked at once | Workbook contains named parameter cells, input validation, a two variable data table, lookup driven outputs, and conditional formatting | BO-5, SN-4 |
| BR-24 | The solution shall present the top exposed products in a single view answering the renewal decision directly | M | The committee has one decision; the default view should answer it without configuration | Landing view ranks products by concentration and exposure without the user changing a filter | BO-1, BO-2, SN-3 |
| BR-25 | The solution shall provide an interactive scenario tool allowing routing weights to be varied live | C | Useful in a meeting, not necessary for the decision | Tool deployed and linked | BO-2 |

### 8.6 Operation and reproducibility

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-26 | The solution shall be reproducible from a clean clone using documented commands only | M | An analysis that only runs on one laptop cannot be repeated next renewal cycle | Runbook in README verified once against a clean clone | BO-6 |
| BR-27 | The solution shall refresh on a schedule aligned to the maritime source's publication cadence | M | Manual refresh will not survive contact with a busy analyst | Scheduled job runs weekly after the source refresh window and is gated on data tests passing | BO-6, BO-4 |
| BR-28 | The solution shall keep all credentials out of version control | M | A leaked key on a public repository is both a security and a fair usage failure | No secret present in the working tree or in the full commit history at the point the repository becomes public | BO-6 |
| BR-29 | The solution shall respect the source provider's fair usage terms | M | Losing access mid cycle ends the project | Requests throttled and cached; no interface scraping; a single registered account | BO-6 |
| BR-30 | The solution shall be extensible to additional products without changes to transformation logic | S | The committee's basket changes as the product line changes | A new canonical product is added by editing reference data and rerunning the build, with no change to transformation code | BO-6 |

## 9. Data requirements

| ID | Requirement | Detail |
|---|---|---|
| DR-1 | Bilateral import values by reporter, partner, commodity code, and year | Sufficient granularity to compute partner shares per product per year |
| DR-2 | Classification vintage carried on every record | Required for BR-05 and BR-13 |
| DR-3 | Daily maritime transit and volume estimates per chokepoint | Required for BR-14 and for the exposure denominators |
| DR-4 | A committed product basket definition mapping commodity codes to canonical products | Required for BR-05 and BR-30 |
| DR-5 | A committed concordance bridge between classification vintages | Required for BR-15 |
| DR-6 | A committed routing assumption matrix with stated basis per row | Required for BR-08 |
| DR-7 | Raw landed data held immutable and never edited in place | Required for BR-21 and BR-26 |
| DR-8 | Threshold reference values with source and version recorded | Required for BR-04 |

## 10. Business rules

| ID | Rule |
|---|---|
| BRULE-1 | Concentration is computed on import value shares by partner country, expressed per canonical product per year |
| BRULE-2 | A canonical product is the unit of analysis. Raw commodity codes are inputs to it and are never the grouping key in a published measure |
| BRULE-3 | Any date listed as a source blackout is excluded from published measures and is never treated as a zero |
| BRULE-4 | Any chokepoint period subject to documented signal loss is published with a flag or not published at all. It is never published clean |
| BRULE-5 | Exposure is labelled as an assumption wherever it appears next to a measured figure |
| BRULE-6 | Concentration thresholds follow the cited external guideline. The project does not invent its own bands |
| BRULE-7 | A missing source year is shown as missing. Interpolation is not permitted |

## 11. Assumptions and constraints

Assumptions A-1 through A-6 and constraints are recorded in the project charter, sections 9 and 10, and are not duplicated here. The single assumption worth restating in a requirements context is A-6: routing weights are a judgement. BR-08, BR-09, and BR-10 exist entirely to contain the risk that creates.

## 12. Out of scope for this release

| Item | Reason |
|---|---|
| Tier two and tier three supplier visibility | No public data source supports it |
| Landed cost, tariff, and freight rate modelling | Does not serve the second sourcing and buffer stock decision |
| Forecasting of future concentration or exposure | The decision needs current exposure and its trend, not a projection |
| Importers other than the United States | Doubles the data and concordance work for marginal gain |
| Individual port level analysis | Adds volume without serving the decision |
| Export and re-export flows | Import dependency is the decision subject |

## 13. Glossary

| Term | Definition |
|---|---|
| Basket | A curated group of related products treated as one analytical category |
| Canonical product | The stable analytical identity of a product across classification vintages |
| Chokepoint | A narrow maritime passage through which a large share of seaborne trade must pass |
| Concentration | The degree to which supply of a product is held by few origin countries |
| Exposure | The modelled share of a product's supply that routes through a given chokepoint |
| HHI | Herfindahl-Hirschman Index, the sum of squared market shares, scaled 0 to 10,000 |
| Series break | A discontinuity caused by measurement change rather than by real change in the underlying activity |
| Routing matrix | The documented set of assumptions mapping origin regions to the chokepoints their shipments transit |

## 14. Open questions

| ID | Question | Owner | Needed by | Blocks |
|---|---|---|---|---|
| OQ-1 | Do all candidate commodity codes exist in the chosen classification vintage with meaningful US import value? | Analyst | Verification | BR-01, scope table |
| OQ-2 | What is the latest available year for US import data? | Analyst | Verification | BR-12 |
| OQ-3 | Where do classification breaks actually appear in the record counts? | Analyst | Verification | BR-13 |
| OQ-4 | Which chokepoints do the two baskets plausibly transit? | Analyst | Ingest | BR-07, BR-08 |
| OQ-5 | Which disruption gives the cleanest event study for these baskets? | Analyst | Measures | BR-14 |
| OQ-6 | Which threshold guideline version is current, and what are its bands? | Analyst | Measures | BR-04 |

No requirement above is baselined as final until OQ-1 and OQ-2 are answered. If either answer contradicts the scope table, this document goes to version 1.1 before any model is written against it.

## 15. Traceability

Every requirement ID in section 8 appears in `docs/05_traceability_matrix.md`, linked forward to a functional specification in `docs/03_frd.md`, to a test case in `docs/06_uat_test_plan.md`, and to the artefact that satisfies it. A requirement with no forward link is either descoped with a recorded reason or the build is not finished.

## 16. Approval

| Role | Name | Date | Decision |
|---|---|---|---|
| Analyst and author | Akash A | 2026-09-14 | Baselined |
| Sponsor (simulated) | Supply chain risk committee | 2026-09-14 | Approved |

> Simulated sign off. The stakeholder is a constructed scenario used to keep scope disciplined, stated plainly so nothing in this repository misrepresents itself as client work.
