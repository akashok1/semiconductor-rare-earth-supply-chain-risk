# Business Requirements Document: Import Concentration Risk

| Field | Value |
|---|---|
| Project name | Import Concentration Risk |
| Document ID | `docs/02_brd.md` |
| Version | 1.1 |
| Status | Rebaselined post-Verification |
| Author | Akash A, Business Analyst |
| Date | 2026-09-18 |
| Related documents | `docs/01_project_charter.md` (v1.1), `docs/03_frd.md`, `docs/05_traceability_matrix.md`, `docs/07_assumptions_limitations.md` |

**Version history**

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-09-13 | Draft from project brief | Akash A |
| 1.0 | 2026-09-14 | Baselined ahead of the Verification phase | Akash A |
| 1.1 | 2026-09-18 | Rebaselined against Verification findings. BR-08 and BR-10 changed subject: routing is computed rather than assigned, and the sensitivity test now targets the proximity threshold. BR-06's hypothesis recorded as disproven. DR-5 retraced from BR-15 to BR-05, BR-12 and BR-13. BR-31 to BR-33 added for vessel share disclosure, concordance validation, and structural absence. Section 14 open questions OQ-1 to OQ-4 closed | Akash A |

> This document states **what the business needs and why**. It does not state how the solution is built. Models, tests, endpoints, and schemas live in the FRD. Every requirement here carries an ID that the traceability matrix uses to connect a business need to a functional specification, a test case, and a shipped artefact.
>
> Requirement IDs are stable across versions. A requirement whose subject changed in 1.1 keeps its ID and carries a note saying what changed, so the traceability matrix does not silently lose a link.

---

## 1. Executive summary

The supply chain risk committee of a mid-size US electronics manufacturer must decide, before annual contract renewals, where to qualify a second supplier and where to hold buffer inventory. It currently has no measure of how concentrated the global supply of its inputs is, and no measure of how exposed that supply is to a maritime chokepoint disruption.

This project delivers a measured concentration and exposure model for two product baskets, built on public trade and maritime data, surfaced in a dashboard and a scenario workbook, with every assumption documented and tested.

The distinction that runs through this document: concentration is **measured**, exposure is **modelled**. Requirements are written so a reader can always tell which is which. Verification narrowed the modelled part considerably. Routing is now computed from shortest sea routes rather than assigned by judgement, and the mode and coast shares that scale it are measured from Census data. One free parameter remains, the 200km proximity threshold, and BR-10 exists for it.

Verification also established that the two baskets behave differently. Semiconductors and semiconductor manufacturing equipment move 70 to 98 percent by air. Rare earths and permanent magnets move 57 to 75 percent by containerized vessel. Exposure is therefore a substantive measure for one basket and a marginal one for the other, and BR-31 exists so that a near zero exposure figure reads as a finding rather than as a defect.

## 2. Business context

The committee buys two categories where supply is known anecdotally to be geographically narrow: semiconductors with their manufacturing equipment, and rare earths with permanent magnets. Both categories moved sharply in the trade policy environment of the last several years.

How they travel was assumed in version 1.0 and measured during Verification. The assumption was that both baskets route predominantly through the South China Sea and the Strait of Malacca. That is wrong. Most semiconductor value flies. Of the value that sails, East Asia to US West Coast routes cross the open Pacific rather than Malacca. Across 30 tested origin and destination pairs, Panama is the most crossed chokepoint at 10, then Gibraltar and Windward Passage at 7, then Malacca at 6. The Pacific chokepoints that matter for these baskets are Taiwan Strait, Korea Strait, Tsugaru and Luzon. The Strait of Hormuz, which dominates chokepoint discussion in the trade press, is crossed by none of the 30 routes and is overwhelmingly tanker traffic.

The committee's existing view is limited to its own purchase orders. Purchase orders show the immediate vendor, not the upstream production base. A contract with a diversified distributor can sit on top of a single country of origin.

## 3. Current state

| Aspect | Current state | Consequence |
|---|---|---|
| Concentration visibility | Vendor level only, from internal purchasing records | A single origin country behind multiple vendors is invisible |
| Routing visibility | None | Chokepoint risk is discussed only after it appears in the news |
| Mode visibility | None | Air freight and sea freight are discussed as one thing, so maritime risk is applied to goods that fly |
| Trend visibility | None | Committee cannot distinguish a worsening dependency from a stable one |
| Basis of discussion | Anecdote and recent headlines | Second sourcing spend follows salience, not exposure |
| Repeatability | Ad hoc analyst pulls | Last year's numbers cannot be reproduced or compared |

## 4. Future state

The committee opens a dashboard before the renewal cycle and, for every input in scope, reads: how concentrated global supply is, how that has moved since 2018, how much of that input actually travels by sea, which chokepoints the seaborne portion routes through, and which part of the exposure figure rests on a stated parameter rather than a measurement. The underlying pipeline refreshes weekly without manual work, and any number on screen can be traced to a source file and a transformation.

## 5. Business objectives

| ID | Objective | Measure of success |
|---|---|---|
| BO-1 | Replace anecdotal concentration discussion with a measured index | Concentration metrics available for 100% of in scope products and years |
| BO-2 | Make maritime routing risk explicit and arguable | Exposure score per product per chokepoint, computed from measured mode shares, measured coast shares, and computed route crossings, with the one remaining parameter sensitivity tested |
| BO-3 | Enable comparison over time | Continuous series from 2018 to 2025 across both classification vintages, with vintage and sensor breaks flagged |
| BO-4 | Make outputs trustworthy | All published source data anomalies encoded as automated tests that fail the build, and no external reference table trusted without validation |
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
| SN-7 | Risk committee | Know when a low risk score means low risk and when it means the measure does not apply | BO-2, BO-4 |

SN-5 is the reason this document distinguishes measurement from assumption everywhere. A recommendation that cannot be challenged will not be funded. SN-7 was added in 1.1: an exposure score near zero for a basket that flies is correct, and a reader who cannot tell that apart from a broken join will discount every number next to it.

## 7. Scope summary

In scope and out of scope are fixed in section 5 of the project charter v1.1 and are not restated here. The material changes at 1.1: the product set is 22 verified HS6 codes rather than an estimated 35, the year range is 2018 to 2025 spanning two classification vintages, and all 28 chokepoints are ingested with crossings computed rather than assumed. Requirements below apply only within that boundary.

## 8. Business requirements

Priority uses MoSCoW. **M** must have for this release, **S** should have, **C** could have, **W** will not have this time.

### 8.1 Supplier concentration

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-01 | The solution shall measure supplier concentration for each product in each year using the Herfindahl-Hirschman Index, computed on partner shares of US import value | M | HHI distinguishes one dominant supplier from two comparable ones; a top share figure cannot | HHI present for every product and year combination in range; values fall between 0 and 10,000; HHI reconciles to a manual calculation for one sampled product and year | BO-1, SN-1 |
| BR-02 | The solution shall report top supplier share, top three supplier share, and supplier count alongside HHI | M | Procurement reads a share figure intuitively; HHI needs interpretation. Both are reported and the difference explained | All four measures present for every product and year; the data dictionary explains why both families are shown | BO-1, SN-3 |
| BR-03 | The solution shall identify the top supplier country for each product and year | M | The decision is country specific, not just concentration specific | Named partner country present for every product and year | BO-1, SN-3 |
| BR-04 | The solution shall classify concentration against published thresholds, citing the guideline source and version used | M | A number without a threshold gives the committee no action trigger | Threshold bands and the guideline version recorded in the data dictionary and shown on the dashboard | BO-1, SN-5 |
| BR-05 | The solution shall group measures by a canonical product identifier rather than by raw commodity code | M | Codes split, merge, and retire across classification vintages; grouping by raw code silently breaks the series. Verification confirmed this is not hypothetical: 854140 and 854150 both retire in 2021 | Every mart aggregates on canonical product; no mart groups on a raw HS code | BO-3 |
| BR-06 | The solution shall report concentration separately for raw rare earth inputs and for downstream permanent magnets | S | **Changed in 1.1.** Version 1.0 hypothesised that concentration worsens downstream. Measurement disproved it: 280530 reaches HHI 9,749 at 98.7 percent China in 2023 against 850511 at HHI 6,413 and 79.8 percent China. The requirement stands because the comparison is informative; the hypothesis is recorded as disproven rather than deleted | Both sub groups appear as distinct canonical products and are separately readable on the dashboard. The 280530 figure carries its value base caveat, under $50M a year | BO-1, SN-1 |

### 8.2 Chokepoint exposure

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-07 | The solution shall produce an exposure score for each product against each in scope maritime chokepoint | M | The committee needs to connect a dependency to a physical route | Score present for every product and chokepoint pair in scope, including pairs where no route crosses. A computed zero is published as a finding, not omitted | BO-2, SN-2 |
| BR-08 | The solution shall compute routing from shortest sea routes between sourced port coordinates and published chokepoint coordinates, and commit the result as inspectable reference data | M | **Changed in 1.1.** Version 1.0 required a hand assigned routing assumption matrix with a stated basis per row, on the grounds that no source links products to routes. Verification established that routes can be computed, which removes the project's largest subjective input. The requirement to make it inspectable and editable without touching logic is unchanged | `routing_matrix.csv` committed with one row per origin, destination and chokepoint combination including non-crossings, carrying the measured distance and the threshold applied. Port and chokepoint coordinates committed with their source recorded per row | BO-2, SN-5 |
| BR-09 | The solution shall state explicitly that exposure is a modelled estimate, naming what it ignores | M | Presenting a modelled figure as a measured one destroys the credibility of the measured figures next to it | Statement present on the dashboard, in the README, and in the assumptions and limitations document. It names, at minimum: routing substitution and carrier behaviour, transshipment, air freight which is not routed, land trade which has no maritime exposure, and the use of one representative port per country | BO-2, SN-5 |
| BR-10 | The solution shall report how much the exposure ranking changes when the proximity threshold is varied | M | **Changed in 1.1.** Version 1.0 varied the routing weights, which no longer exist as a free input. The threshold is now the only free parameter in the routing computation, and a ranking that flips under a small change in it is not a basis for spending money | Sensitivity result published showing the exposure ranking at 50, 100, 200 and 300km, with any change in rank order named explicitly | BO-2, SN-5 |
| BR-11 | The solution shall allow the committee to view exposure filtered to a single chokepoint | S | The committee's questions arrive chokepoint first when an event is in the news | Chokepoint filter available on the dashboard, covering all 28 including those with no crossings | BO-2, SN-2 |

### 8.3 Trend and event history

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-12 | The solution shall present concentration for each product as a continuous annual series from 2018 to 2025 | M | A single year cannot distinguish a worsening dependency from a stable one | Series renders with no missing years; missing source years are labelled as missing, never interpolated; the series crosses the 2021 to 2022 vintage boundary without a break in the canonical product | BO-3, SN-1 |
| BR-13 | The solution shall flag any year where a classification change affects comparability | M | A concordance artefact that looks like a real shift will be read as one. Verification located the break precisely: US data is HS2017 through 2021 and HS2022 from 2022 | Affected years visibly flagged in the mart and annotated on the dashboard. An automated test asserts value continuity across the vintage boundary for every canonical product that changed codes | BO-3, BO-4 |
| BR-14 | The solution shall include one event study examining chokepoint traffic before and after a real disruption | M | Demonstrates that the maritime data responds to real events, which is what makes the exposure model plausible at all | One event study published with the disruption named, the comparison window stated, and the limits of the inference stated. The chokepoint studied must be one the baskets actually cross | BO-2, BO-3 |
| BR-15 | The solution shall extend the concentration series to earlier classification vintages | C | Longer history strengthens trend reading but does not change this year's decision. Note: the bridge table infrastructure this depends on is now built for a different reason, so the marginal cost of this requirement has fallen | Additional years present with vintage labelled | BO-3 |

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
| BR-24 | The solution shall present the top exposed products in a single view answering the renewal decision directly | M | The committee has one decision; the default view should answer it without configuration | Landing view ranks products by concentration and exposure without the user changing a filter, and shows vessel share coverage beside each exposure figure so the two baskets are not compared on a measure that applies unequally | BO-1, BO-2, SN-3, SN-7 |
| BR-25 | The solution shall provide an interactive scenario tool allowing the proximity threshold to be varied live | C | Useful in a meeting, not necessary for the decision. Subject changed in 1.1 in line with BR-10 | Tool deployed and linked | BO-2 |

### 8.6 Operation and reproducibility

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-26 | The solution shall be reproducible from a clean clone using documented commands only | M | An analysis that only runs on one laptop cannot be repeated next renewal cycle | Runbook in README verified once against a clean clone | BO-6 |
| BR-27 | The solution shall refresh on a schedule aligned to the maritime source's publication cadence | M | Manual refresh will not survive contact with a busy analyst | Scheduled job runs weekly after the source refresh window and is gated on data tests passing | BO-6, BO-4 |
| BR-28 | The solution shall keep all credentials out of version control | M | A leaked key on a public repository is both a security and a fair usage failure | No secret present in the working tree or in the full commit history at the point the repository becomes public. Applies to both the Comtrade and the Census key | BO-6 |
| BR-29 | The solution shall respect each source provider's fair usage terms | M | Losing access mid cycle ends the project | Requests throttled and cached; no interface scraping; a single registered account per source. Every response cached on first pull so a rerun costs zero calls | BO-6 |
| BR-30 | The solution shall be extensible to additional products without changes to transformation logic | S | The committee's basket changes as the product line changes | A new canonical product is added by editing reference data and rerunning the build, with no change to transformation code | BO-6 |

### 8.7 Measurement integrity (new in 1.1)

| ID | Requirement | Priority | Rationale | Acceptance criteria | Traces to |
|---|---|---|---|---|---|
| BR-31 | The solution shall state, beside every exposure figure, what share of that product's import value travels by containerized vessel | M | Exposure covers only the seaborne share. Semiconductor codes run 70 to 98 percent air, one at 99.2 percent, so an exposure figure near zero is a correct finding about air freight and not a model failure. Without the coverage figure a reader cannot tell the two apart | Vessel share coverage present in the exposure mart and displayed wherever an exposure score is shown. The asymmetry between the two baskets stated on the dashboard and in the README | BO-2, BO-4, SN-7 |
| BR-32 | The solution shall validate every external concordance or reference mapping against trade value continuity before relying on it | M | Published concordances are not authoritative. The UN Stats HS2022 to HS2017 correlation table names an unrelated telephone code as sole predecessor of both HS2022 successors of 854150, which if trusted would have removed a $825M code from the series after 2021. It was caught only by checking the values | Every mapping in the bridge table carries its basis. Where a published table was overridden, the row states that the resolution is empirical and names the evidence. A continuity test across the vintage boundary runs as part of the build | BO-4, SN-5 |
| BR-33 | The solution shall distinguish a structurally absent code from missing data | M | A code that retired in 2021 has no 2022 value, and a code introduced in 2022 has no 2018 value. Neither is a gap. Rendering them as gaps makes a complete series look broken and invites interpolation, which BRULE-7 forbids | A status field distinguishing active, retired and introduced codes is present in the bridge and carried into the marts. No dashboard view renders a structurally absent year as missing data | BO-3, BO-4, SN-7 |

## 9. Data requirements

| ID | Requirement | Detail |
|---|---|---|
| DR-1 | Bilateral import values by reporter, partner, commodity code, and year | Sufficient granularity to compute partner shares per product per year |
| DR-2 | Classification vintage carried on every record | Required for BR-05 and BR-13 |
| DR-3 | Daily maritime transit and volume estimates per chokepoint | Required for BR-14 and for chokepoint vessel mix evidence |
| DR-4 | A committed product basket definition mapping commodity codes to canonical products, with an include or exclude decision per candidate code | Required for BR-05 and BR-30 |
| DR-5 | A committed concordance bridge between classification vintages, with a status field and a stated basis per row | **Retraced in 1.1.** Previously traced to BR-15 at priority C. US import data is HS2017 through 2021 and HS2022 from 2022, so without the bridge the series stops in 2021. Now required for BR-05, BR-12, BR-13, BR-32 and BR-33, all M |
| DR-6 | A committed routing matrix with computed crossing results and measured distances, covering every origin, destination and chokepoint combination | **Changed in 1.1.** Previously a hand assigned matrix with a stated basis per row. Required for BR-07, BR-08 and BR-10 |
| DR-7 | Raw landed data held immutable and never edited in place | Required for BR-21 and BR-26 |
| DR-8 | Threshold reference values with source and version recorded | Required for BR-04 |
| DR-9 | Measured mode of transport shares and port of entry shares per commodity code per year, covering air, vessel, containerized vessel, and the land residual | **New in 1.1.** Required for BR-07, BR-09 and BR-31. Comtrade reports total mode of transport only for the US, so this must come from a second trade source |
| DR-10 | Sourced geographic coordinates for origin ports, US destination ports, and chokepoints, each carrying its source | **New in 1.1.** Required for BR-08. No coordinate may be entered by hand without a recorded source |

## 10. Business rules

| ID | Rule |
|---|---|
| BRULE-1 | Concentration is computed on import value shares by partner country, expressed per canonical product per year |
| BRULE-2 | A canonical product is the unit of analysis. Raw commodity codes are inputs to it and are never the grouping key in a published measure |
| BRULE-3 | Any date listed as a source blackout is excluded from published measures and is never treated as a zero |
| BRULE-4 | Any chokepoint period subject to documented signal loss is published with a flag or not published at all. It is never published clean |
| BRULE-5 | Exposure is labelled as modelled wherever it appears next to a measured figure |
| BRULE-6 | Concentration thresholds follow the cited external guideline. The project does not invent its own bands |
| BRULE-7 | A missing source year is shown as missing. Interpolation is not permitted |
| BRULE-8 | Air value and land value are removed from the exposure denominator, never routed. Both remain in every concentration measure |
| BRULE-9 | A year in which a commodity code did not exist, or had already retired, is not a missing year and is not subject to BRULE-7 |
| BRULE-10 | No external concordance or reference mapping is used without validation against the data it claims to describe. Where a published table conflicts with measured value continuity, the measurement wins and the override is recorded |
| BRULE-11 | HHI for a canonical product spanning several commodity codes is computed on summed partner values across those codes. It is never the average of the component codes' HHIs |

## 11. Assumptions and constraints

Assumptions A-1 through A-8 and constraints are recorded in the project charter v1.1, sections 9 and 10, and are not duplicated here.

Version 1.0 said that the single assumption worth restating in a requirements context was that routing weights are a judgement, and that BR-08, BR-09 and BR-10 existed to contain that risk. That assumption is retired. Routing is computed. Two assumptions took its place and both remain untestable with public data: A-3, that a shortest sea route resembles the route actually sailed, and A-7, that a radius around a published point coordinate represents transit of a strait. BR-09 states both, and BR-10 tests the one that has a number attached.

## 12. Out of scope for this release

| Item | Reason |
|---|---|
| Tier two and tier three supplier visibility | No public data source supports it |
| Air freight routing | The air share is measured per code, but no public source gives air corridors or transfer hubs at commodity level. Air value is removed from the exposure denominator rather than routed |
| Land border trade routing | Land trade has no maritime chokepoint exposure. Mexico and Canada imports are 95.5 and 74.8 percent land respectively. Excluded from exposure, retained in concentration |
| Transshipment and carrier routing substitution | Not separable in any public source. Recorded as a limitation under A-3 |
| Landed cost, tariff, and freight rate modelling | Does not serve the second sourcing and buffer stock decision |
| Forecasting of future concentration or exposure | The decision needs current exposure and its trend, not a projection |
| Importers other than the United States | Doubles the data and concordance work for marginal gain |
| Individual port level analysis | Adds volume without serving the decision. 28 chokepoints, not 2,065 ports |
| Export and re-export flows | Import dependency is the decision subject |
| Mirror statistics | Imports are valued CIF and exports FOB, so the two records of one shipment never reconcile. US reported imports only |
| Partial year data | Annual frequency only. A partial year makes every share a fraction of an incomplete denominator |

## 13. Glossary

| Term | Definition |
|---|---|
| Basket | A curated group of related products treated as one analytical category |
| Canonical product | The stable analytical identity of a product across classification vintages |
| Chokepoint | A narrow maritime passage through which a large share of seaborne trade must pass |
| Code status | Whether a commodity code is active, retired at a vintage boundary, or introduced at one. Distinguishes a structural absence from missing data |
| Concentration | The degree to which supply of a product is held by few origin countries. Measured |
| Exposure | The modelled share of a product's seaborne supply that routes through a given chokepoint |
| HHI | Herfindahl-Hirschman Index, the sum of squared market shares, scaled 0 to 10,000 |
| Mode share | The proportion of a code's import value arriving by air, by vessel, or across a land border. Measured |
| Proximity threshold | The distance within which a sea route is treated as transiting a chokepoint. The one free parameter in the routing computation |
| Routing matrix | The computed set of results recording, for each origin, destination and chokepoint, whether the shortest sea route passes within the threshold, and at what distance |
| Series break | A discontinuity caused by measurement change rather than by real change in the underlying activity |
| Vessel share coverage | The proportion of a product's import value that an exposure figure actually applies to |
| Vintage break | The year at which a commodity code changed under a classification revision |

## 14. Open questions

Closed during Verification, evidence in `docs/07_assumptions_limitations.md`:

| ID | Question | Answer |
|---|---|---|
| OQ-1 | Do all candidate commodity codes exist in the chosen vintage with meaningful US import value? | Yes. 22 codes verified, all above the value floor. The version 1.0 estimate of roughly 35 was arithmetic error, not a filter |
| OQ-2 | What is the latest available year for US import data? | 2025 |
| OQ-3 | Where do classification breaks actually appear? | At 2021 to 2022. US data is HS2017 through 2021 and HS2022 from 2022. 854140 splits four ways, 854150 splits two ways, the other 20 codes carry over unchanged |
| OQ-4 | Which chokepoints do the two baskets plausibly transit? | Computed rather than assumed. 13 of 28 are crossed by at least one of 30 tested routes. Panama 10, Gibraltar and Windward Passage 7 each, Malacca 6. Hormuz zero |

Still open:

| ID | Question | Owner | Needed by | Blocks |
|---|---|---|---|---|
| OQ-5 | Which disruption gives the cleanest event study for the chokepoints these baskets actually cross? | Analyst | Measures | BR-14 |
| OQ-6 | Which threshold guideline version is current, and what are its bands? | Analyst | Measures | BR-04 |
| OQ-7 | Does the exposure ranking hold at 50, 100 and 300km? | Analyst | Analysis and BI | BR-10 |
| OQ-8 | Is 854151's jump from $18M to $179M in 2025 a real shift or a classification migration? | Analyst | Post release | BR-13, informational |

## 15. Traceability

Every requirement ID in section 8 appears in `docs/05_traceability_matrix.md`, linked forward to a functional specification in `docs/03_frd.md`, to a test case in `docs/06_uat_test_plan.md`, and to the artefact that satisfies it. A requirement with no forward link is either descoped with a recorded reason or the build is not finished.

BR-08, BR-10 and BR-25 changed subject at version 1.1 and kept their IDs. Any traceability link written against their 1.0 wording must be reread against the 1.1 wording before the matrix is closed.

## 16. Approval

| Role | Name | Date | Decision |
|---|---|---|---|
| Analyst and author | Akash A | 2026-09-18 | Rebaselined |
| Sponsor (simulated) | Supply chain risk committee | 2026-09-18 | Approved |

> Simulated sign off. The stakeholder is a constructed scenario used to keep scope disciplined, stated plainly so nothing in this repository misrepresents itself as client work.
