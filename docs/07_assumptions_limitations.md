# Assumptions, exclusions and corrections

Working reference for the Semiconductor and Rare Earth Supply Chain Risk build. Records what was
assumed, what was tested, what changed as a result, and what remains
unverifiable. Kept current as the build proceeds.

Last updated: 2026-09-26

---

## 1. Data sources

| Source | What it gives | Access | Used for |
|---|---|---|---|
| UN Comtrade | Annual US import value by partner country and HS6 code, 2018 to 2025 | API, free tier key, 500 calls/day | Every dollar figure and every concentration measure |
| US Census international trade | Monthly US imports by HS6 and country with general, air, vessel and containerized vessel values (imports/hs), and vessel value by US port of entry (imports/porths) | API, free key | Each country's containerized vessel value and each code's total import value (the exposure numerator and denominator), and each code's coast shares |
| IMF PortWatch | Chokepoints database (28 points with coordinates); daily transit counts and capacity by vessel type per chokepoint, 2019 onward; ports database (2,065 ports with portid, ISO3, coordinates, container vessel counts and country maritime trade shares; one undated snapshot) | ArcGIS REST, no key | Chokepoint list and coordinates; origin and US destination port coordinates; within-country port weights; transits held for a future disruption case study, read by no current mart |
| searoute (Eurostat network) | Shortest sea route between two points, computed over a pre-built ocean mesh with Dijkstra | Python package, computed locally, no API | Which chokepoints a route between two ports passes near |

Static reference documents, cached as files rather than queried:

| Document | Used for |
|---|---|
| Census Schedule D port and district codes | Classifying US ports of entry into coastal regions and land borders |
| UN Stats HS correlation tables | Mapping HS2017 codes to HS2022 codes in the bridge table |
| USGS Mineral Commodity Summaries, Interior critical minerals list | Justifying rare earth basket selection |
| Commerce semiconductor supply chain review | Justifying semiconductor basket selection |
| European Commission (2021), *Strategic dependencies and capacities* (SWD(2021) 352) | The HHI 0.4 (4,000) concentration criterion used as the 2x2 line. Not the DOJ/FTC merger bands: those describe firm market power, not supplier-country dependence |

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

**Exposure** is modelled, from Census plus computed routes, per HS6 code,
year, chokepoint and distance threshold. It is computed per HS6 code, not
per canonical product, because vessel share diverges between successor
codes (854140's successors range from 2.75% to 95.2% containerized vessel).
It is grouped under its canonical product for display, never blended.

```
exposure = sum over countries c of
             cnt_val(code, c, year) x routing_weight(code, c, chokepoint)
           / gen_val(code, year, all countries, all modes)

routing_weight = sum over coasts k (west, east, gulf) of
             coast_share(code, year, k)
           x sum over ports p of country c of
               port_weight(p, c)
             x crosses(p, US port of k, chokepoint, threshold)

port_weight(p, c) = share_country_maritime_export(p), normalized over
             c's ports with vessel_count_container > 0
```

| Term | Source | Kind |
|---|---|---|
| `cnt_val(code, c, year)` | Census imports/hs, country c's own containerized vessel value | Measured |
| `gen_val(code, year)` | Census imports/hs, general imports, all countries and all modes | Measured |
| `coast_share(code, year, k)` | Census imports/porths vessel value by US port, classified to coast by Schedule D district with manual port overrides | Measured |
| `port_weight(p, c)` | PortWatch ports database, computed in dbt | Measured weight, normalization is a modelling choice |
| `crosses(...)` | `min_distance_km <= threshold` on `routing_matrix`, computed in dbt at 50, 100, 200 and 300km | Computed |

- `cnt_val` is each country's own containerized vessel value. A code-level
  vessel share is never applied to every partner: that would give
  land-dominant partners (Mexico, 95.8% land) fake maritime exposure.
- Air and land value stay in the denominator and are never routed. No
  public source gives air corridors or land routing at commodity level.
- `coast_share` is per code only. Census vessel value by port carries no
  country, so a German and a Chinese shipment of the same code get the same
  coast split. Disclosed limitation.
- Countries without PortWatch ports are routed through a gateway country's
  port weights (section 3.1). Territories with no plausible gateway are
  unrouted.

**Parameters and sensitivity.** Two modelling choices are stated as
parameters and sensitivity tested at the exposure mart:

- **Distance threshold.** 200km is the headline; 50, 100 and 300km are the
  sensitivity range (A-7).
- **Port weighting.** `share_country_maritime_export` is the headline
  weight. It has no documented unit and covers all cargo, not containers
  only: summed over a country's container ports it falls below 95 for 63
  of 174 countries, hence the normalization. `vessel_count_container`,
  normalized the same way, is the sensitivity weight (A-4).

The other judgement inputs are the manual reference CSVs, each row with a
reason: the landlocked gateways, one US destination port per coast, and the
district to coast map with its port overrides.

**Reported alongside every exposure figure**, never silently zeroed:

- vessel coverage: `cnt_val / gen_val`, the share of the code's value that
  the figure can speak to at all;
- unrouted share: containerized value from countries with no route;
- coast residual: vessel value landing outside the three coasts (interior
  and Great Lakes ports; coast shares sum to 0.948 to 1.000).

Exposure is labelled as modelled wherever it sits next to measured
concentration.

**Worked example.** 854143 (photovoltaic modules), 2025, headline
weighting, from `fct_exposure_summary`: $6.39B general import value,
98.5% of it containerized vessel, 0% unrouted, coast residual 0.01%. The
largest suppliers by containerized value are Indonesia ($2.29B), Laos
($1.00B, routed via Thailand), India, Viet Nam and Malaysia, all of which
reach the east and gulf coasts westbound through the Indian Ocean. The
risk-set maximum at 200km is Suez at 95.2% landing east, Panama at 62.1%
landing gulf, Taiwan Strait at 33.7% landing west, and Suez at 52.0%
national (blended by coast share). The all-28 maximum at national is
Gibraltar at 52.1%, which is why the 2x2 reads the risk set (section
2.1). The earlier 850511 and Taiwan Strait example (about 42%) applied a
code-level vessel share to China's import share, which the current
formula forbids, and stays withdrawn.

**What this number is not.** It is not a statement that a share of
shipments physically passed through a strait. It is the share of import
value whose shortest sea route, from its country's container ports to the
US coast it lands on, would pass within the threshold of the chokepoint.
Routing substitution, transshipment and carrier choice are not modelled.

### 2.1 The 2x2 and the dashboard

The dashboard is built by hand in Tableau Public from the CSVs in
`exports/` (written by `make export`). It has four sheets:

| Sheet | Source | What it shows |
|---|---|---|
| 2x2 | `fct_exposure_summary` | One point per HS6 code. x: `hhi`, fixed axis 0 to 10,000. y: `risk_max_exposure_200`, fixed axis 0 to 100%, labelled with `risk_max_chokepoint` |
| Top suppliers | `fct_supplier_share` | Top 10 partners by share for the selected canonical product and year |
| HHI trend | `fct_concentration` | HHI for the selected canonical product, every year 2018 to 2025 |
| Chokepoints | `fct_exposure` | Top 10 chokepoints at 200km with exposure of at least 1%, the risk set coloured apart from the rest, titled "do not add these up" |

Controls are Tableau parameters, not filters, so one control drives all
four sheets: Product, Year (default 2025), Coast (default national), HHI
line (default 4,000) and Exposure line (default 25%). Weighting is fixed
to `export_share` on the dashboard; `vessel_count` is a sensitivity
reported in section 3.2, not a control.

**Axes.** HHI line at 4,000 is the European Commission (2021) concentration
criterion (HHI 0.4). `effective_suppliers` (10,000 / HHI) is in the
tooltip. The y-axis is the largest single-chokepoint exposure at 200km
over the risk set in `data/reference/manual/chokepoint_risk_set.csv`
(Suez, Bab el-Mandeb, Panama, Hormuz, Taiwan Strait, each with its
documented disruption). The all-28 maximum (`flow_` columns) is drilldown
only: it picks funnels with no disruption record (Gibraltar, Tsugaru,
Yucatan). It is never a sum across chokepoints, which double counts, and
never a union over all 28, which collapses to vessel share because 82% of
routes cross at least one chokepoint at 200km.

**Quadrants**, computed in Tableau:

| Condition | Label | Action |
|---|---|---|
| Risk-set exposure at 100km and at 300km fall on opposite sides of the exposure line | Distance sensitive | Not assigned a quadrant: the call depends on the proximity threshold |
| HHI and exposure both at or above their lines | Buffer stock + second supplier | Build buffer stock now and start qualifying a second supplier |
| HHI only | Qualify second supplier | Country risk is persistent: diversify it |
| Exposure only | Hold buffer stock | Hold buffer stock. If you receive goods on more than one coast, the Coast control shows which coast avoids the chokepoint |
| Neither | Monitor | |

**Coast control** means "where your goods land". A per-coast figure
assumes the importer receives all its sea imports at that coast's ports
(`coast_share` for that coast set to 1). National is the US average,
blended by each code's actual coast shares. Every coast is assumed to
receive the national supplier mix, because no public source splits
supplier country by US coast (Census vessel value by port carries no
country). HHI does not change with the coast.

**Logic that lives in Tableau, not dbt.** Disclosed because it is not
covered by dbt tests:

- Product name labels: a CASE on `hs6_code`.
- The H5 to H6 successor mapping for the supplier and trend sheets: a
  CASE mapping the six HS2022 successors (854141, 854142, 854143, 854149;
  854151, 854159) to their canonical products 854140 and 854150, because
  those two sheets key on `canonical_product_id` while the 2x2 is picked
  by HS6 code.
- The Quadrant calculation above.

---

## 3. Assumptions that were tested

Each of these started as an assumption in the project brief and was replaced
by a measurement.

The verification phase's routing tests on 15 representative ports x 2 US
coasts (30 routes) are superseded by the full routing run in section 3.1
and kept as a historical record in `docs/verification/spike_routing_method.md`.

| Assumption | How it was tested | Result | What changed |
|---|---|---|---|
| Imports arrive predominantly by sea | Comtrade mode of transport field, then Census air and vessel values per HS6 | Comtrade reports TOTAL MOT only for the US. Census shows 70 to 98% air for most semiconductor codes, 20 to 53% air for rare earths. Code 854231 moves $1.59B by vessel against $196.73B total, 0.8% | Exposure routes only each country's own containerized vessel value; air and land value stay in the denominator unrouted. Census added as a third source |
| Downstream magnets are more concentrated than raw rare earths | HHI computed for both, 2023 | The reverse. Raw rare earth metals (280530) reach HHI 9,749 at 98.7% China, magnets (850511) HHI 6,413 at 79.8% | Hypothesis in the brief recorded as disproven. Caveat added that 280530 sits on a small value base, under $50M a year |
| HS2017 covers 2018 to the latest year | Queried Comtrade classification vintage by year for reporter USA | US data is native H5 through 2021 and H6 from 2022. Querying H5 for later years returns zero rows. 854140 and 854150 split into six HS2022 subheadings | The HS bridge table moved from optional enhancement to first release requirement |
| The unexplained residual in Census mode data might not be land trade (verification phase, 22 HS2017 codes) | Compared the residual against land border port share computed from official Schedule D codes | The two independent measurements agree within 2 percentage points for all 22 codes | Residual confirmed as land trade. Accounting closes: air plus vessel plus land equals total |

### 3.1 Routing method (A-3, A-7, D-8, BR-10)

Routing is computed, not hand assigned, and replaces the verification
phase's 15 representative ports x 2 US coasts (30 routes, kept in
`docs/verification/spike_routing_method.md` as a historical record).

**Origins.** Every foreign port in the PortWatch ports database with
`vessel_count_container > 0`: 1,253 ports in 174 countries. There is no
representative port per country. Ports are keyed on PortWatch `portid` and
ISO3, never LOCODE. Within a country, each port is weighted by its
`share_country_maritime_export`, normalized over that country's container
ports. The weights are computed in dbt, not in `ingest/routing.py`;
`vessel_count_container` is the sensitivity weight (section 2).

**Countries without PortWatch ports.** Landlocked or portless countries are
routed through a gateway country's port weights, one row each with a reason
in `data/reference/manual/landlocked_gateways.csv` (13 gateways, e.g. Laos
via Thailand, Ethiopia via Djibouti, Switzerland via the Netherlands).
Territories with no plausible gateway (British Indian Ocean Territory,
Tokelau) carry a blank gateway and are reported as unrouted, never silently
zeroed.

**Destinations.** One US port per coast, in
`data/reference/manual/us_destination_ports.csv`: Los Angeles-Long Beach
(west), New York-New Jersey (east), Houston (gulf). Each is the largest
Census port on its coast by 2018-2025 basket vessel value. Coast shares come
from Census vessel value by port of entry, per HS6 code.

**Geometry.** `searoute` (Eurostat marnet, local, no API) gives the shortest
sea route for every origin x coast pair: 3,759 routes, all computed, none
failed. For each route and each of the 28 PortWatch chokepoints,
`routing_matrix` stores `min_distance_km`: the distance from the chokepoint
to the nearest point on the route line, measured in an azimuthal
equidistant projection centred on the chokepoint. It stores distance only.
There is no crossing flag in the generated file.

**Thresholds.** `crosses = min_distance_km <= threshold` is computed in dbt
at 50, 100, 200 and 300km. 200km is the headline; the others are the
sensitivity test.

Routes (of 3,759) passing within each threshold of each chokepoint, from
`raw.routing_matrix`:

| Chokepoint | 50km | 100km | 200km | 300km |
|---|---|---|---|---|
| Panama Canal | 1,486 | 1,493 | 1,493 | 1,493 |
| Gibraltar Strait | 943 | 949 | 955 | 958 |
| Mona Passage | 590 | 605 | 663 | 674 |
| Windward Passage | 406 | 532 | 539 | 546 |
| Yucatan Channel | 489 | 489 | 495 | 495 |
| Suez Canal | 361 | 364 | 370 | 376 |
| Tsugaru Strait | 306 | 306 | 333 | 342 |
| Bab el-Mandeb Strait | 319 | 319 | 319 | 322 |
| Oresund Strait | 225 | 231 | 279 | 309 |
| Korea Strait | 18 | 234 | 261 | 285 |
| Malacca Strait | 161 | 167 | 182 | 186 |
| Bosporus Strait | 159 | 162 | 174 | 174 |
| Taiwan Strait | 120 | 129 | 141 | 242 |
| Dover Strait | 99 | 99 | 123 | 151 |
| Luzon Strait | 0 | 101 | 101 | 104 |
| Strait of Hormuz | 78 | 87 | 87 | 87 |
| Bohai Strait | 45 | 48 | 60 | 69 |
| Sunda Strait | 41 | 41 | 48 | 48 |
| Cape of Good Hope | 45 | 45 | 45 | 51 |
| Kerch Strait | 39 | 39 | 42 | 48 |
| Torres Strait | 0 | 39 | 39 | 39 |
| Balabac Strait | 32 | 32 | 34 | 36 |
| Makassar Strait | 28 | 28 | 33 | 33 |
| Ombai Strait | 19 | 26 | 26 | 28 |
| Magellan Strait | 22 | 22 | 25 | 25 |
| Lombok Strait | 3 | 8 | 14 | 14 |
| Mindoro Strait | 0 | 0 | 11 | 18 |
| Bering Strait | 0 | 0 | 0 | 6 |
| Chokepoints crossed by at least one route | 24 | 26 | 27 | 28 |

Panama, Gibraltar, Yucatan, Bab el-Mandeb and Hormuz barely move across
the range. Korea Strait (18 to 234 between 50 and 100km), Luzon Strait (0
to 101), Windward Passage (406 to 532) and Taiwan Strait (141 to 242
between 200 and 300km) are threshold sensitive. The East Asian ones sit on
the transpacific routes, so the parameter matters most where Asian vessel
value is largest. Hormuz is crossed by 87 routes at 200km, all from Persian
Gulf origins; no other origin crosses it.

These are unweighted route counts. They say which chokepoints enter or leave
the crossing set at each threshold, not how the exposure ranking changes.
The value-weighted answer is in section 3.2.

**Known limitations.** Disclosed, not fixed.

- Chokepoints are points while straits are hundreds of km long. Port Klang
  to New York sails the Malacca Strait but passes 219.6km from its point,
  so it misses at the 200km headline and crosses only at 300km.
- Ports near a chokepoint count as crossing it. Kaohsiung sits 77km from the
  Taiwan Strait point, so every Kaohsiung route crosses it at 100km and
  above whichever way it sails.
- Routes are static shortest paths. Red Sea diversions via the Cape of Good
  Hope from late 2023 are not modelled.
- Goods shipped to Mexican or Canadian ports and trucked into the US count
  as land and are never routed.
- searoute snaps each port to its network before routing. 101 ports snap
  more than 100km, including four Brazilian river ports at 520 to 1,078km.
  The skipped leg is inland or coastal and passes no chokepoint, so
  chokepoint distances are unaffected.
- coast_share is per code only, because Census vessel value by port carries
  no country. A German and a Chinese shipment of the same code get the same
  coast split.
- Port weights come from one undated PortWatch ports database snapshot,
  applied unchanged to every year from 2018 to 2025. A country whose
  export mix shifted between its ports over the period is weighted as it
  stands in the snapshot. PortWatch daily chokepoint transits (2019 on)
  are loaded into raw and staged, but no mart reads them.
- The Suez and Bab el-Mandeb figures assume the Red Sea route is open.
  Carriers have diverted Asia to US east coast services via the Cape of
  Good Hope since late 2023, so for 2024 and 2025 those figures describe
  the shortest-path exposure, not the route sailed. 854143's 52.0%
  national Suez figure for 2025 is the largest case.

### 3.2 Sensitivity results (BR-10, D-8, A-4)

Both tests read `fct_exposure_summary` at the dashboard defaults (HHI line
4,000, exposure line 25%, risk-set y-axis), all 26 HS6 codes live in 2025
and every code-year from 2018.

**Distance threshold.** A point is distance sensitive when the same
chokepoint's exposure at 100km and at 300km falls on opposite sides of
the 25% line. In 2025 no point is distance sensitive at any coast. Across
2018 to 2025 there are 10, all landing west and all Taiwan Strait:
854140 (2018), 854190 (2019 to 2023), 854142 (2022 to 2024) and 848610
(2023). Each sits under 25% at 200km and crosses it only at 300km,
consistent with Taiwan Strait's jump from 141 to 242 routes between 200
and 300km (section 3.1). No national point is distance sensitive in any year.

**Port weighting.** Swapping `export_share` for `vessel_count` weighting
moves exactly one point across a line, in any year or coast: 854142
landing gulf in 2025, Panama at 25.8% under `export_share` and 24.9%
under `vessel_count`, so Hold buffer stock becomes Monitor. At national,
no code in any year changes quadrant. Flagged counts for 2025 under
`export_share` / `vessel_count`: national 8 / 8, east 10 / 10, gulf
10 / 9, west 5 / 5.

**2025 at the defaults, national, `export_share`.** 8 of 26 codes are
flagged:

| Quadrant | Codes (risk-set chokepoint, exposure at 200km) |
|---|---|
| Buffer stock + second supplier | 280530 (HHI 6,924; Panama 46.0%) |
| Qualify second supplier | 284610 (HHI 5,657; Panama 20.0%), 850511 (HHI 5,364; Panama 15.6%) |
| Hold buffer stock | 854143 (Suez 52.0%), 854190 (Bab el-Mandeb 39.9%), 848610 (Panama 37.1%), 848630 (Panama 30.7%), 284690 (Panama 25.8%; HHI 3,764, near both lines) |
| Monitor | The other 18 |

### 3.3 What a supplier share means here

- **Supplier is country of origin, not mining origin.** Comtrade records
  the country of last substantial transformation. 284610's top supplier
  in 2023 to 2025 is Japan (69% to 73%): a processed rare earth compound,
  not mined ore. The HHI measures who ships the processed good to the US,
  not who mines the input (A-1).
- **HS2022 successors inherit family-level concentration.** 854140 and
  854150 split in 2022, but Comtrade concentration is computed per
  canonical product, so all four 854140 successors carry the same HHI and
  supplier table, and so do both 854150 successors. The family's top
  supplier need not be the top supplier of any one successor: in 2025
  854140's top supplier is Indonesia (29.7%), and the solar module points
  (854142, 854143) show that family-level figure, not a solar-only one.
  Exposure, by contrast, is per HS6 code.
- **280530 is tiny.** Raw rare earth metals are $8.2M of US imports in
  2025 ($22.1M in 2023, $4.7M in 2024). Its HHI (6,924 in 2025, 9,749 at
  98.7% China in 2023) is real but sits on a value base where one
  shipment moves the share.
- **Only rare earths clear the line in 2025, not in every year.** All
  three canonical products at or above HHI 4,000 in 2025 are rare earth
  products (280530, 284610, 850511), and 280530 and 850511 are above it
  in every year from 2018 to 2025. Earlier years add non-rare-earth
  products: 854231 (processors) at 4,040 in 2019 and 4,137 in 2020, and
  848610 at 4,030 in 2019. 284690 is above 4,000 in six of eight years
  and 284610 from 2020 on.

---

## 4. Assumptions still standing

These cannot be tested with available public data. Each is stated wherever
the affected number appears.

| ID | Assumption | Why it cannot be tested | Effect if wrong |
|---|---|---|---|
| A-1 | Country of origin approximates production origin | Comtrade records last substantial transformation, not corporate or upstream supply chain structure | Concentration is understated. Malaysia at 33% of integrated circuits is assembly and test of wafers fabricated elsewhere, so true fabrication concentration is higher than measured |
| A-2 | Comtrade partner code 490, "Other Asia, nes", is Taiwan | Taiwan is not a UN member and is reported as a residual category | Minor. The category is overwhelmingly Taiwan, but it is a convention rather than a measurement |
| A-3 | Shortest sea route approximates the route actually sailed | No public dataset links a shipment to a route. The searoute authors state the tool is built for realistic looking routes rather than navigation | Exposure attributed to the wrong chokepoint where carriers deviate for cost, weather, congestion or alliance routing |
| A-4 | A country's containerized exports to the US leave from its container ports in proportion to each port's `share_country_maritime_export`, normalized over the country's ports with `vessel_count_container > 0` | Comtrade and Census give partner country, not port of loading. The PortWatch share covers all cargo and all destinations, not containers bound for the US | Crossings misweighted within countries whose ports sit on different seas, e.g. northern versus southern China relative to the Taiwan Strait. Tested by rerunning exposure with `vessel_count_container` as the weight |
| A-5 | Import value share is a reasonable proxy for physical dependency | No public source gives unit volumes consistently across products | Products with volatile prices show concentration shifts that reflect price, not supply. Net weight is reported alongside value as a partial check |
| A-6 | Chokepoint transit counts reflect route activity | Documented AIS signal loss and transponder suppression in some regions | Affected chokepoints are flagged rather than used as reliable volumes |
| A-7 | A 200km radius around a chokepoint's published point coordinate captures transit of that chokepoint | PortWatch publishes each chokepoint as a single point, but a chokepoint is an area. The Strait of Malacca alone runs roughly 800km, so exact intersection would be meaningless and some radius is required | A threshold too tight drops real crossings, too loose invents them. Treated as a stated parameter and sensitivity tested at the exposure mart |

---

## 5. Exclusions

| Excluded | Reason |
|---|---|
| Tier two and tier three supplier visibility | No public dataset supports it. Trade data measures shipments between countries, not corporate ownership |
| Air freight routing | Census measures the air share, but no public source gives air corridors or transfer hubs at commodity level. Air and land value stay in the exposure denominator and are never routed |
| Land border trade routing | Mexico and Canada imports are 95.8% and 75.2% land respectively across the 28 basket HS6 codes, 2018 to 2025 (`dbt/analyses/mexico_canada_mode_split.sql`). Land trade has no maritime chokepoint exposure and is excluded from exposure, not from concentration. Mode residual (general value not carried by air or vessel) from non-neighbour countries, Malaysia $2.49B over 2018 to 2025 (`dbt/analyses/residual_by_country.sql`), is consistent with transshipment through Mexican or Canadian ports; it is likewise unrouted and stays in the denominator |
| Individual ports as a unit of analysis | The PortWatch ports database (2,065 ports) is used as an input: coordinates for origin and US destination ports, and within-country port weights. Ports are not reported or ranked in their own right; exposure is reported per chokepoint only |
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
| Origin port coordinates entered by hand | Flagged in review as an unsourced input | Resolved from the UN/LOCODE dataset, fetched and cached, source documented in the script. Since replaced by the PortWatch ports database |
| WCO correlation table names 851712 (cellular telephones) as sole predecessor of both 854151 and 854159 | Checked directly against the Conversions tab: 854150 never appears as a named predecessor for anything, and the sheet is structurally one-predecessor-per-code with zero merged cells, zero blank-predecessor continuation rows and no code listed twice, so this is the table's own automated matching failing, not a parse artifact | Resolved empirically by Census import-value continuity across the 2021/2022 break instead of trusting the table: 854150 at $825.9M in 2021 against 854151+854159 at $819.9M in 2022, a 0.7% gap |

### 6.1 854150 to 854151/854159: the correlation table was wrong, resolved by value continuity

854150 (HS2017, "other semiconductor devices") has no HS2022 successor in the
UN Stats correlation workbook that a reasonable process would accept.

Source: `HS2022toHS2017ConversionAndCorrelationTables.xlsx`, UN Stats
Economic Statistics classifications page. Resolved download URL, verified
with no redirect:
`https://unstats.un.org/unsd/classifications/Econ/tables/HS2022toHS2017ConversionAndCorrelationTables.xlsx`.
Fetched and cached 2026-09-18, `data/raw/un_hs2022_to_hs2017_correlation.xlsx`.

The workbook ships two tabs. "HS2022-HS2017 Conversions" names exactly one
HS2017 predecessor per current HS2022 code (5,613 rows, 5,613 distinct
codes, verified). In that tab, HS2022 854151 and HS2022 854159 both name
HS2017 **851712** (cellular telephones) as their sole predecessor. 854150
does not appear as a named predecessor of anything, anywhere in the tab.
"HS2022-HS2017 Correlations" (the broader overlap tab) shows 854150 only in
six `n:n` rows against 854921/854929/854931/854939/854991/854999, the new
HS2022 8549 heading ("electrical and electronic waste and scrap") -- noise
from that heading's from-scratch automated matching, not a real relation.

This was checked as a possible parsing artifact and ruled out. The
Conversions tab was re-parsed with `openpyxl` (added as a dependency for
this reason) after an initial hand-rolled zipfile/xml.etree parser was
suspected of shifting rows around blank cells. The suspicion did not hold:
the hand-rolled parser already tracked each cell's `r=` reference. The
openpyxl re-parse returned the identical 851712 result. A further check for
the specific failure mode of multi-predecessor entries spread across
continuation rows (HS2022 code in column A, additional HS2017 predecessors
on blank-column-A rows beneath it) found none: zero merged cell ranges in
the Conversions tab, zero rows with a blank column A and populated column
B, and zero HS2022 codes appearing on more than one row. The tab is
structurally one predecessor per code by design. It cannot express two
predecessors even if it wanted to, and for 854151/854159 it names the wrong
one. This is the WCO's own automated nearest-match algorithm failing on a
heavily restructured chapter, not anything on the ingest side.

Resolved instead by US Census import value (`GEN_VAL_YR`, `SUMMARY_LVL ==
'DET'` rows, December year-to-date, `-` sentinel excluded, same methodology
as section 1):

| Year | 854150 | 854151 | 854159 |
|---|---|---|---|
| 2018 | $426,101,475 | no data | no data |
| 2019 | $399,686,598 | no data | no data |
| 2020 | $403,983,599 | no data | no data |
| 2021 | $825,916,060 | no data | no data |
| 2022 | no data | $24,800,504 | $795,140,052 |
| 2023 | no data | $21,096,047 | $1,137,743,658 |
| 2024 | no data | $17,958,080 | $906,382,542 |
| 2025 | no data | $178,763,927 | $994,153,849 |

854150 goes to exactly zero after 2021; 854151 and 854159 are both exactly
zero through 2021 and pick up in 2022. Combined 854151+854159 in 2022 is
$819,940,556 against 854150's final year of $825,916,060, a 0.7% gap. HS
nomenclature text supports the mechanism: 854159 keeps 854150's old "other
semiconductor devices" title verbatim, and 854151 is new for
"semiconductor-based transducers," added to the 8541 heading text in the
HS2022 revision. 851712 has no plausible mechanism to be a predecessor of
either. The resolution and its evidence live in
`data/reference/manual/bridge_overrides.csv`, one row per successor code;
`hs_bridge.py` applies it and the generated `hs_bridge.csv` rows point back
to that file. It is not recorded as a WCO table finding.

### 6.2 Vintage-break value continuity, all 22 basket codes

Ran the same H5-2021-vs-H6-2022 continuity check used on 854150 against all
22 basket codes, most of which did not change HS number across the
2017/2022 revision:

| H5 code | 2021 (H5) | 2022 (H6 sum) | Gap | Successors |
|---|---|---|---|---|
| 854110 | $531,246,612 | $750,719,127 | +41.3% | 854110 |
| 854121 | $131,835,401 | $175,177,682 | +32.9% | 854121 |
| 854129 | $1,514,664,868 | $1,936,021,907 | +27.8% | 854129 |
| 854130 | $70,947,246 | $120,448,204 | +69.8% | 854130 |
| 854140 | $9,137,638,899 | $12,403,236,792 | +35.7% | 854141+854142+854143+854149 |
| 854150 | $825,916,060 | $819,940,556 | -0.7% | 854151+854159 |
| 854160 | $339,135,164 | $417,731,505 | +23.2% | 854160 |
| 854190 | $378,762,939 | $481,980,782 | +27.3% | 854190 |
| 854231 | $27,344,302,869 | $24,326,886,346 | -11.0% | 854231 |
| 854232 | $2,194,656,387 | $2,755,894,264 | +25.6% | 854232 |
| 854233 | $644,023,397 | $886,809,727 | +37.7% | 854233 |
| 854239 | $10,414,858,777 | $15,017,269,087 | +44.2% | 854239 |
| 854290 | $310,056,969 | $380,081,272 | +22.6% | 854290 |
| 848610 | $67,590,503 | $176,697,863 | +161.4% | 848610 |
| 848620 | $4,284,479,839 | $6,414,677,975 | +49.7% | 848620 |
| 848630 | $4,839,547 | $5,999,735 | +24.0% | 848630 |
| 848640 | $581,503,681 | $925,984,109 | +59.2% | 848640 |
| 848690 | $3,686,042,058 | $4,063,166,597 | +10.2% | 848690 |
| 280530 | $17,256,523 | $17,687,095 | +2.5% | 280530 |
| 284610 | $28,081,846 | $27,487,065 | -2.1% | 284610 |
| 284690 | $105,192,401 | $160,803,240 | +52.9% | 284690 |
| 850511 | $490,985,694 | $639,542,567 | +30.3% | 850511 |

Control group argument, offered as an inference, not a proof: most codes in
this table did not change HS number across the revision and still show a
+23% to +70% gap. That band is best read as the 2021-to-2022 semiconductor
market (the chip shortage price and demand surge), not as evidence of
bridge failure, because it appears just as strongly on codes with no
classification event to explain it. On that reading, 854140's +35.7%
combined gap sits inside the band its unchanged peers occupy and is not, by
itself, a sign of a bad partition. This is an inference supported by the
control group, not something proven here.

Two things fall outside that reading and are flagged only, not
investigated:

- **848610 at +161.4%** sits well outside the +23% to +70% band the other
  unchanged codes occupy. Unexplained.
- **854231 fell 11.0% while 854239 rose 44.2%** across the same boundary,
  an opposite-signed move between a specific code and what is normally a
  residual "other" code in the same heading, consistent with classification
  drift between the two rather than a market effect. Both codes are
  unchanged self-maps per the correlation table (no HS number change), so
  if there is drift it would be happening at the reporting/coding level, not
  the classification-table level.

---

## 7. Data quality rules

The PortWatch rules are published by IMF PortWatch; the Comtrade and Census
rules were verified in the raw data. Only the Comtrade World rule is a dbt
test (`assert_comtrade_partners_sum_to_world`). The PortWatch rules are not
built: they govern the daily transits, which no mart reads, and are carried
forward to the event study. The Census sentinel is filtered in
`stg_census_hs`, but its equality to the DET rows is not asserted by a
test.

| Issue | Handling |
|---|---|
| Blackout dates 2022-05-12, 2023-02-14, 2024-01-09 | Excluded from the clean mart. Test asserts zero rows on those dates |
| GPS jamming and spoofing near the Strait of Hormuz | Flagged and caveated. Volumes not treated as reliable |
| Transponder suppression in sanctioned regions | Affected chokepoints and periods flagged |
| 2021 receiver coverage expansion causing a step change at Gwangyang and Malacca | Flagged as a series break, never presented as growth |
| Strait of Hormuz boundary revised February 2026 | Data version pinned. Series labelled as not comparable across the revision |
| A missing source year | Shown as missing. Interpolation is not permitted |
| Comtrade partner 0 (World) | Excluded at staging. In raw it equals the sum of partner rows exactly, per code per year; asserted by `assert_comtrade_partners_sum_to_world` |
| Census `'-'` sentinel | Excluded at staging, although tagged DET. In raw it equals the sum of the DET rows, within $1 for all 192 code-years (verified by query, not a dbt test) |

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

- ~~Verify that the HS2017 to HS2022 split of 854140 and 854150 is a clean partition, using the UN correlation tables. Check that summed H6 value for 2022 is continuous with H5 value for 2021.~~ Done, see sections 6.1 and 6.2. 854140 is a clean 4-way partition per the correlation table. 854150 is not resolvable via the correlation table at all (it names 851712 as predecessor of both successors); resolved empirically by value continuity instead.
- ~~Record the current DOJ and FTC Merger Guidelines version and its HHI threshold bands.~~ Replaced: the 2x2 line is the European Commission (2021) HHI 0.4 criterion (section 2.1). Merger bands describe firm market power, not supplier-country dependence.
- ~~Sensitivity test the 200km proximity threshold.~~ Done, section 3.2. Tested as quadrant changes at the 25% line between 100 and 300km, not as a full rank-order comparison.
- ~~Sensitivity test the port weighting.~~ Done, section 3.2: one point moves in any year or coast (854142, gulf, 2025).
- ~~Run the concentration series across all years.~~ Done, `fct_concentration` covers 2018 to 2025. 280530's China share fell from 98.7% (2023) to 78.2% (2024) and 82.5% (2025); the drop predates China's April 2025 rare earth export controls and is not attributed to them. 284690's China share fell from 74.5% to 58.6% in 2025 while France rose from 5.8% to 15.5%, consistent with the controls, which name yttrium and scandium compounds under 2846 codes.
- Event study (D-7, BR-14). Not built. PortWatch transits and the "RED SEA TENSIONS" disruption rollup are loaded for it.
- PortWatch data-quality tests (section 7). Not built, deferred with the event study.
- Encode the vintage-break value-continuity check (section 6.2) as a dbt test: summed H6 value for a canonical product's first H6 year against its last H5 year, flagged past a tolerance. Satisfies BR-13.
