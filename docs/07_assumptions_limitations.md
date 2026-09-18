# Assumptions, exclusions and corrections

Working reference for the Import Concentration Risk build. Records what was
assumed, what was tested, what changed as a result, and what remains
unverifiable. Kept current as the build proceeds.

Last updated: 2026-09-17

---

## 1. Data sources

| Source | What it gives | Access | Used for |
|---|---|---|---|
| UN Comtrade | Annual US import value by partner country and HS6 code, 2018 to 2025 | API, free tier key, 500 calls/day | Every dollar figure and every concentration measure |
| US Census international trade | Monthly US imports by HS6 with air, vessel, containerized vessel values, and port of entry | API, free key | Mode of transport shares and port of entry shares, held as reference multipliers |
| IMF PortWatch | Daily transit counts and capacity by vessel type for 28 maritime chokepoints, 2019 onward, plus chokepoint point coordinates from a separate spatial layer | ArcGIS REST, no key | Chokepoint list and coordinates, vessel mix evidence, event study |
| searoute (Eurostat network) | Shortest sea route between two points, computed over a pre-built ocean mesh with Dijkstra | Python package, computed locally, no API | Which chokepoints a route between two ports passes near |

Static reference documents, cached as files rather than queried:

| Document | Used for |
|---|---|
| UN/LOCODE, improved republication filling official coordinate gaps from OpenStreetMap | Resolving origin and destination port coordinates. Official UN/LOCODE has no coordinates for Kaohsiung, among others |
| Census Schedule D port and district codes | Classifying US ports of entry into coastal regions and land borders |
| UN Stats HS correlation tables | Mapping HS2017 codes to HS2022 codes in the bridge table |
| USGS Mineral Commodity Summaries, Interior critical minerals list | Justifying rare earth basket selection |
| Commerce semiconductor supply chain review | Justifying semiconductor basket selection |
| DOJ and FTC Merger Guidelines | HHI threshold bands, version cited |

All API responses are cached under `data/raw/` on first pull and read from
cache on rerun. `data/raw/` is immutable and gitignored. A rerun costs zero
API calls.

---

## 2. The exposure formula

Concentration is measured. Exposure is modelled. The two are never presented
as the same kind of number.

**Concentration**, per canonical product per year, from Comtrade alone:

```
partner_share = partner_import_value / total_import_value
HHI           = sum(partner_share^2) * 10,000
```

Reported alongside top supplier share, top three share, supplier count, and
the named top supplier country.

For a canonical product spanning several HS codes, partner values are summed
across those codes first and shares computed on the total. HHI of a combined
product is not the average of its components' HHIs.

**Exposure**, per canonical product per chokepoint per year:

```
exposure = sum over partners of [
      partner_share_of_import_value          (Comtrade, measured)
    x containerized_vessel_share_of_that_code (Census, measured)
    x routing_weight(partner, chokepoint)     (searoute, computed)
]
```

where

```
routing_weight = sum over US coasts of [
      coast_share_of_that_code's_vessel_value   (Census, measured)
    x 1 if the shortest sea route from that partner's representative port
        to that coast passes within 200km of the chokepoint, else 0
]
```

Every term is measured or computed. No term is assigned by judgement. The
only free parameter is the 200km proximity threshold, treated as a stated
parameter and sensitivity tested when the exposure mart is built.

**Worked example, permanent magnets (850511) and the Taiwan Strait:**

China holds roughly 80% of import value. 56.6% of 850511 value arrives by
containerized vessel. Of that vessel value, 75.9% enters via West Coast ports
and 17.5% via East Coast. Sea routes from Chinese ports to both coasts pass
near the Taiwan Strait. So China contributes roughly
0.80 x 0.566 x 0.934 = 0.42, meaning about 42% of magnet import value sits on
routes transiting the Taiwan Strait, before adding other partners.

**What this number is not.** It is not a statement that 42% of shipments
physically passed through that strait. It is the share of import value whose
shortest sea route would transit it. Routing substitution, transshipment and
carrier choice are not modelled.

---

## 3. Assumptions that were tested

Each of these started as an assumption in the project brief and was replaced
by a measurement.

| Assumption | How it was tested | Result | What changed |
|---|---|---|---|
| Imports arrive predominantly by sea | Comtrade mode of transport field, then Census air and vessel values per HS6 | Comtrade reports TOTAL MOT only for the US. Census shows 70 to 98% air for most semiconductor codes, 20 to 53% air for rare earths. Code 854231 moves $1.59B by vessel against $196.73B total, 0.8% | Exposure applies only to the measured containerized vessel share of each code, not to total import value. Census added as a third source |
| Both baskets route via Malacca and the South China Sea | Computed shortest sea routes from 15 supplier ports to 2 US ports, intersected with chokepoint coordinates | East Asia to US West Coast crosses the open Pacific. Across 30 routes, Panama is the most crossed at 10, then Gibraltar and Windward Passage at 7, Malacca at 6. Gibraltar, Suez and Bab el-Mandeb appear only for European, Israeli and Indian origins | Routing matrix rebuilt around the chokepoints the routes actually cross. Relevant Pacific chokepoints are Taiwan Strait, Korea Strait, Tsugaru and Luzon |
| Downstream magnets are more concentrated than raw rare earths | HHI computed for both, 2023 | The reverse. Raw rare earth metals (280530) reach HHI 9,749 at 98.7% China, magnets (850511) HHI 6,413 at 79.8% | Hypothesis in the brief recorded as disproven. Caveat added that 280530 sits on a small value base, under $50M a year |
| Routing weights must be assigned by judgement | Tested whether searoute could compute routes and whether crossings could be detected against chokepoint coordinates | Routes compute and crossings detect correctly. 15 of 28 chokepoints are crossed by no tested route, including the Strait of Hormuz | Routing matrix became computed rather than hand assigned. This removes the project's largest subjective input |
| Nearest vertex distance is an adequate proxy for route proximity | Reimplemented using true nearest point on the route line, in an azimuthal equidistant projection centred on each chokepoint, and compared both methods on all 30 routes | No crossings differ. The vertex method happened to be correct because the Eurostat mesh places dense nodes at straits, so a route transiting a chokepoint almost always has a vertex there | Method replaced anyway. The result is now correct by construction rather than by node placement. Validated first against a synthetic case where a segment passed 2.2km from a point while both its vertices sat over 284km away |
| HS2017 covers 2018 to the latest year | Queried Comtrade classification vintage by year for reporter USA | US data is native H5 through 2021 and H6 from 2022. Querying H5 for later years returns zero rows. 854140 and 854150 split into six HS2022 subheadings | The HS bridge table moved from optional enhancement to first release requirement |
| Chokepoint risk in the news is relevant to these baskets | Vessel mix per chokepoint from PortWatch, and route crossings | The Strait of Hormuz is crossed by zero of 30 tested routes and is overwhelmingly tanker traffic | Hormuz retained only as a contrast case. Two independent lines of evidence, geometry and vessel mix, reach the same conclusion |
| The unexplained residual in Census mode data might not be land trade | Compared the residual against land border port share computed from official Schedule D codes | The two independent measurements agree within 2 percentage points for all 22 codes | Residual confirmed as land trade. Accounting closes: air plus vessel plus land equals total |
| Port coordinates entered by hand are good enough inside a 200km threshold | Replaced with coordinates resolved from the UN/LOCODE dataset for all 15 origins and both US destinations | Coordinates now sourced and citable | No hand entered coordinate remains in the project. Which port represents each country is still an editorial choice, recorded in the script |

---

## 4. Assumptions still standing

These cannot be tested with available public data. Each is stated wherever
the affected number appears.

| ID | Assumption | Why it cannot be tested | Effect if wrong |
|---|---|---|---|
| A-1 | Country of origin approximates production origin | Comtrade records last substantial transformation, not corporate or upstream supply chain structure | Concentration is understated. Malaysia at 33% of integrated circuits is assembly and test of wafers fabricated elsewhere, so true fabrication concentration is higher than measured |
| A-2 | Comtrade partner code 490, "Other Asia, nes", is Taiwan | Taiwan is not a UN member and is reported as a residual category | Minor. The category is overwhelmingly Taiwan, but it is a convention rather than a measurement |
| A-3 | Shortest sea route approximates the route actually sailed | No public dataset links a shipment to a route. The searoute authors state the tool is built for realistic looking routes rather than navigation | Exposure attributed to the wrong chokepoint where carriers deviate for cost, weather, congestion or alliance routing |
| A-4 | One representative port stands for a whole country's exports | Comtrade gives partner country, not port of loading | Crossings misattributed for large countries with coasts on different seas. China routed from Shanghai, so southern Chinese exports may route differently |
| A-5 | Import value share is a reasonable proxy for physical dependency | No public source gives unit volumes consistently across products | Products with volatile prices show concentration shifts that reflect price, not supply. Net weight is reported alongside value as a partial check |
| A-6 | Chokepoint transit counts reflect route activity | Documented AIS signal loss and transponder suppression in some regions | Affected chokepoints are flagged rather than used as reliable volumes |
| A-7 | A 200km radius around a chokepoint's published point coordinate captures transit of that chokepoint | PortWatch publishes each chokepoint as a single point, but a chokepoint is an area. The Strait of Malacca alone runs roughly 800km, so exact intersection would be meaningless and some radius is required | A threshold too tight drops real crossings, too loose invents them. Treated as a stated parameter and sensitivity tested at the exposure mart |

---

## 5. Exclusions

| Excluded | Reason |
|---|---|
| Tier two and tier three supplier visibility | No public dataset supports it. Trade data measures shipments between countries, not corporate ownership |
| Air freight routing | Census measures the air share, but no public source gives air corridors or transfer hubs at commodity level. Air value is removed from the exposure denominator rather than routed |
| Land border trade routing | Mexico and Canada imports are 95.5% and 74.8% land respectively. Land trade has no maritime chokepoint exposure and is excluded from exposure, not from concentration |
| Individual ports (2,065 in PortWatch) | Adds volume without serving the decision. Chokepoints only |
| Exports and re-exports | The decision concerns import dependency |
| Importers other than the United States | Doubles data and concordance work for marginal analytical gain |
| Landed cost, tariffs, freight rates | The decision is second sourcing and buffer stock, not cost |
| Forecasting | The model measures exposure as it stands and as it has moved |
| Mirror statistics (partner-reported exports to the US) | Import and export records of the same shipment never reconcile, since imports are valued CIF and exports FOB. US-reported imports only, never mixed |
| Partial year 2026 data | Annual frequency only. A partial year would make every share a fraction of an incomplete denominator |

---

## 6. Corrections made during the build

| What went wrong | How it was caught | Fix |
|---|---|---|
| Comtrade World aggregate row (partner code 0) included in share calculations | Every code returned a top supplier share of exactly 50.0%, which is not plausible ten times in a row | Filter on `partnerCode != 0`. Filtering happens at the staging layer, not at ingest, so raw stays faithful to the source |
| Description columns returned null, so a text based filter on "World" matched nothing | Same symptom as above | `includeDesc=True` on the Comtrade call, and filter on codes rather than text |
| Census summary level rows double counted | For 854231 in 2018, the unfiltered sum was $125.4B against a true $21.6B. Regional groupings such as ASIA and PACIFIC RIM overlap each other and the per-country rows | Require `SUMMARY_LVL == 'DET'` and exclude the `"-"` grand total sentinel, which is also tagged DET. Validated by three way agreement between Census by country, Census by port, and Comtrade |
| Census rejects comma joined commodity codes | A batched request for 22 codes returned HTTP 204, confirmed by testing a 3 code batch in isolation | One call per code, each covering the full monthly range in one request, keeping December rows since year to date fields accumulate |
| Port of entry distribution computed on total import value | Top ports came back as LAX, SFO, Anchorage and Sea-Tac, which are airports, making the table useless for maritime routing | Recomputed on vessel value only |
| Port classification by name keyword | Land border crossings fell into "Unclassified". CBP districts mix seaports with land crossings under one district number, so San Diego contains Otay Mesa and Seattle contains Blaine | Classify by official Schedule D port code with explicit overrides for mixed districts |
| Chokepoint proximity measured to nearest route vertex | Vertex spacing on open ocean segments runs to hundreds of km, so a route can pass close to a chokepoint on a segment and register as a miss | Replaced with true nearest point on the route line, measured in an azimuthal equidistant projection centred on each chokepoint so planar distance from the centre equals great circle distance. No crossings changed on this route set |
| Origin port coordinates entered by hand | Flagged in review as an unsourced input | Resolved from the UN/LOCODE dataset, fetched and cached, source documented in the script |

---

## 7. Data quality rules encoded as tests

Published by IMF PortWatch and encoded as dbt tests that fail the build.

| Issue | Handling |
|---|---|
| Blackout dates 2022-05-12, 2023-02-14, 2024-01-09 | Excluded from the clean mart. Test asserts zero rows on those dates |
| GPS jamming and spoofing near the Strait of Hormuz | Flagged and caveated. Volumes not treated as reliable |
| Transponder suppression in sanctioned regions | Affected chokepoints and periods flagged |
| 2021 receiver coverage expansion causing a step change at Gwangyang and Malacca | Flagged as a series break, never presented as growth |
| Strait of Hormuz boundary revised February 2026 | Data version pinned. Series labelled as not comparable across the revision |
| A missing source year | Shown as missing. Interpolation is not permitted |

Structural rules verified in the data:

- `n_cargo` equals the sum of container, dry bulk, general cargo and roro counts, exactly, for all 78,764 rows. It is an aggregate and is never used beside its components.
- `n_total` equals `n_cargo + n_tanker`, exactly.
- `capacity_*` aggregates differ from their component sums by at most 3 units against a median of 1.41 million, consistent with independent rounding rather than a data problem.
- The vessel type breakdown exists from the first date of the series for all 28 chokepoints. No schema cutover.

---

## 8. Things the analysis cannot support

State these before anyone asks.

- It cannot say that a given shipment passed through a given chokepoint. PortWatch counts ships, not goods, and a container ship carries thousands of unrelated products.
- It cannot see upstream fabrication. A diversified set of origin countries can sit on top of a single fabrication base.
- It cannot measure whether an alternative supplier has spare capacity or could be qualified. It ranks candidate alternates by existing trade volume only.
- It cannot predict future concentration or exposure. It measures the current position and how it has moved.
- It cannot separate price movement from volume movement in value based shares, beyond what net weight reveals.
- It cannot route air freight, which is the majority of the semiconductor basket by value. For those codes the exposure figure covers a small minority of the physical flow, and says so.

---

## 9. Open items

- Verify that the HS2017 to HS2022 split of 854140 and 854150 is a clean partition, using the UN correlation tables. Check that summed H6 value for 2022 is continuous with H5 value for 2021.
- Record the current DOJ and FTC Merger Guidelines version and its HHI threshold bands.
- Build `basket_selection.csv` recording, per candidate code, the external list it appears on, the US net import reliance figure where published, and the decision to include or exclude.
- Sensitivity test the 200km proximity threshold at the exposure mart, reporting whether the exposure ranking changes at 50, 100, 200 and 300km. This satisfies deliverable D-8 and requirement BR-10.
- Run the concentration series across all years once the bridge table exists. No trend has been measured yet, so the question of whether concentration worsened after the 2025 Chinese export restrictions is still open.
