# Semiconductor and Rare Earth Supply Chain Risk

Ahead of annual contract renewals, where should a supply chain risk
committee qualify a second supplier, and where should it hold buffer
stock? This project answers that for US imports of two baskets,
semiconductors with their manufacturing equipment and rare earths with
permanent magnets. It scores every HS6 code on two axes:

- **Supplier concentration** (measured): HHI of US import value by
  partner country, from UN Comtrade.
- **Chokepoint exposure** (modelled): the share of import value whose
  shortest sea route passes within 200km of a disrupted maritime
  chokepoint, from US Census trade by mode and port plus sea routes
  computed from 1,253 origin ports.

Concentration is a measurement. Exposure is a model. The dashboard and
every doc label them that way.

**Terms**

- **HHI**: a 0-10,000 supplier concentration score; 10,000 means one
  supplier. 4,000 is the European Commission (2021) concern line.
- **HS6 code**: a 6-digit customs product code.
- **Chokepoint**: a narrow sea passage such as Suez or Panama.
- **Exposure**: the share of a product's total US import value on a ship
  whose route passes within 200km of a chokepoint. Modelled.
- **Flagged**: in any quadrant other than Monitor.
- **Canonical product**: a product tracked across the 2022 HS code split.

**Dashboard:** _Tableau Public link pending_
**Screenshots:** _pending_

## Headline findings

- **8 of 26 codes flagged in 2025** (US-wide view, headline port
  weighting, default lines HHI 4,000 and exposure 25%). The other 18 are
  Monitor.
- **In 2025, rare earths are the only concentration problem.** All 3 codes above
  HHI 4,000 in 2025 are rare earth inputs (280530 rare earth metals 6,924,
  284610 cerium compounds 5,657, 850511 permanent magnets 5,364). 280530
  and 850511 are above 4,000 every year 2018-2025. 280530 peaked at 98.7%
  China in 2023.
- **Chips fly.** Processors and controllers (854231) move under 1% of
  their value by sea every year 2018-2025. Maritime chokepoints barely
  touch them.
- **Routing:** 1,253 origin ports in 174 countries, routed to three US
  coasts and measured against 28 chokepoints.
- **Census double count caught:** processors' 2018 imports summed to
  $125.4B against a true $21.6B, because Census regional rollups and a
  grand-total row are tagged as detail rows. Caught by reconciling Census
  by country, Census by port and Comtrade against each other.
- **97 dbt tests (13 custom), all passing.**

### 2025 at the default lines (national)

| Quadrant | Codes | Action |
|---|---|---|
| Buffer stock + second supplier | 280530 (Panama 46.0%) | Build buffer stock now and start qualifying a second supplier |
| Qualify second supplier | 284610, 850511 | Country risk is persistent: diversify it |
| Hold buffer stock | 854143 solar modules (Suez 52.0%), 854190 (Bab el-Mandeb 39.9%), 848610 (Panama 37.1%), 848630 (Panama 30.7%), 284690 (Panama 25.8%) | Hold buffer stock. If you receive goods on more than one coast, the Coast control shows which coast avoids the chokepoint |
| Monitor | The other 18 codes | |
| Distance sensitive | None in 2025 | |

Read these with their caveats:

- 280530 is about $8M of imports in 2025. Its concentration is real but
  its dollar stake is small.
- 284690 sits near both lines (HHI 3,764, exposure 25.8%).
- Only in 2025 are the concentration flags all rare earths. Processors
  (854231) cleared 4,000 in 2019 and 2020, and 848610 in 2019.
- The Suez and Bab el-Mandeb figures are on the shortest path. Carriers
  have routed via the Cape of Good Hope since late 2023.
- Supplier means country of origin, not mining origin. 284610's top
  supplier is Japan, shipping processed material.

## The dashboard

Built by hand in Tableau Public from the four CSVs in `exports/`.

| Sheet | Source | Shows |
|---|---|---|
| 2x2 | `fct_exposure_summary` | One point per HS6 code. x: HHI, fixed 0-10,000. y: largest exposure to one risky chokepoint, fixed 0-100% |
| Top suppliers | `fct_supplier_share` | Top 10 partner countries for the canonical product |
| HHI trend | `fct_concentration` | HHI for every year 2018-2025 |
| Chokepoints | `fct_exposure` | Top 10 chokepoints at 200km with exposure of at least 1%, the risk set (the five chokepoints with a documented disruption) coloured apart from the rest, titled "do not add these up" |

Five parameters drive all four sheets: Product, Year (default 2025),
Coast (default national), HHI line (default 4,000) and Exposure line
(default 25%).

- **HHI line.** 4,000 is the European Commission (2021) *Strategic
  dependencies and capacities* criterion (HHI 0.4), not the DOJ/FTC
  merger bands, which describe firm market power.
- **Exposure axis.** The largest exposure at 200km to a single chokepoint
  in the risk set: Suez, Bab el-Mandeb, Panama, Hormuz and Taiwan Strait,
  each with a documented disruption. It is never a sum across
  chokepoints, because one route crosses several and a sum double counts.
- **Distance sensitive.** When the same chokepoint's exposure at 100km
  and at 300km fall on opposite sides of the exposure line, the point is
  not assigned a quadrant.
- **Coast** means "where your goods land". A per-coast view assumes all
  sea imports land at that coast. National is the US average weighted by
  actual coast shares. Every coast is assumed to receive the national
  supplier mix, because no public data splits supplier country by coast.
  HHI does not change with the coast.
- **Port weighting** is fixed to each port's share of its country's
  exports. Weighting by container ship count instead is a sensitivity,
  reported in `docs/07` §3.2: it moves one point in any year or coast
  (854142 landing gulf in 2025).
- **Logic in Tableau, not dbt:** product name labels (a CASE on HS6),
  the mapping of the six HS2022 successor codes to 854140 and 854150 for
  the supplier and trend sheets, and the quadrant calculation.

## Method

**Concentration.** HHI = 10,000 x the sum of squared partner shares of
US import value, per canonical product per year, from Comtrade. A product
spanning several HS codes sums partner values across codes first. The
World row is excluded; partner 490 ("Other Asia, nes") is Taiwan.

**Exposure**, per HS6 code, year, chokepoint and threshold:

```
exposure = sum over countries c of cnt_val(c) x routing_weight(c, chokepoint)
           / gen_val(all countries, all modes)
```

`cnt_val` is each country's own containerized vessel value from Census,
so land-dominant suppliers (Mexico is 95.8% land) get no maritime
exposure. Air and land stay in the denominator and are never routed.
`routing_weight` blends the three US coasts by each code's measured coast
share and weights every container port in the supplier country by its
PortWatch share of the country's maritime exports. Crossing means the
`searoute` shortest path passes within the threshold (50, 100, 200 or
300km; 200 is the headline) of the PortWatch chokepoint point. Countries
without ports route through a named gateway (Laos via Thailand).
Vessel coverage, unrouted share and coast residual are reported beside
every exposure figure.

The 2x2 y-axis is `risk_max_exposure_200` in `fct_exposure_summary`: the
largest single-chokepoint exposure at 200km over the risk set in
`data/reference/manual/chokepoint_risk_set.csv`. The port weighting is
`export_share` (PortWatch `share_country_maritime_export`, the headline)
or `vessel_count` (`vessel_count_container`, the sensitivity).

**HS vintages.** US data is HS2017 through 2021 and HS2022 from 2022. A
bridge maps every code to a canonical product. 854150's successors were
resolved by Census value continuity (0.7% gap) because the UN correlation
table names cellular telephones as their predecessor. Concentration is
per canonical product; exposure is per HS6 code, because successors'
vessel shares range from 2.75% to 95.2%.

Full derivations, sensitivity results and every correction are in
[`docs/07_assumptions_limitations.md`](docs/07_assumptions_limitations.md).

## Data sources

| Source | Gives |
|---|---|
| UN Comtrade | US imports by partner and HS6, 2018-2025 |
| US Census international trade | Imports by country with air, vessel and containerized value; vessel imports by US port |
| IMF PortWatch | 28 chokepoints, 2,065-port database with container counts and export shares, daily transits |
| searoute (Eurostat marnet) | Shortest sea routes, computed locally |
| UN Stats HS2022-HS2017 correlation tables | Starting point for the HS bridge |

## Architecture

```
ingest (Python) -> Postgres raw (immutable) -> dbt staging -> intermediate -> marts -> exports/*.csv -> Tableau Public
```

Python only calls APIs, parses files and computes route geometry. Every
share, weight, HHI and exposure is computed in dbt. Every API response
is cached under `data/raw/` on first pull, so a rerun costs zero calls.
Refresh is manual: Comtrade and Census are annual, and so is the
decision.

## Running it from a clean clone

Requires Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker, and
free API keys for [UN Comtrade](https://comtradeplus.un.org/) and the
[Census Bureau](https://api.census.gov/data/key_signup.html).

```bash
git clone https://github.com/akashok1/semiconductor-rare-earth-supply-chain-risk.git
cd semiconductor-rare-earth-supply-chain-risk
uv sync
cp .env.example .env   # set the API keys and Postgres credentials
docker compose up -d   # Postgres on port 5433
make all               # bridge, comtrade, census, portwatch, routing, load, dbt-build
make export            # marts -> exports/*.csv for Tableau
```

`make all` runs, in order: `bridge` (HS bridge), `comtrade`, `census`,
`portwatch`, `routing` (searoute over every container port), `load` (raw
files into Postgres `raw.*`) and `dbt-build` (seeds, models, tests).
Pass flags with `ARGS`, e.g. `make comtrade ARGS="--refresh 2025"`.
After a seed's columns change, run `make dbt-seed-full` first.

## Tests

13 custom dbt tests in `dbt/tests/`, plus 84 uniqueness, not-null and
accepted-values tests in the `schema.yml` files: 97 in total, all passing
(`make dbt-test`). The custom tests cover:
Comtrade partners summing to the World row, every partner matched to a
name, supplier shares summing to 1, HHI in 0-10,000, port weights summing
to 1, every weighted port routed to every coast, crossing shares in 0-1,
coast vessel totals matching the port table, exposure within vessel
coverage, national exposure within coast coverage, every code-year
present in the 2x2, the risk set matching PortWatch names, and the HS
vintage boundary matching the bridge.

## Docs

| Doc | Status |
|---|---|
| [`docs/07_assumptions_limitations.md`](docs/07_assumptions_limitations.md) | Current record: formula, dashboard decisions, sensitivity, corrections |
| [`docs/04_data_dictionary.md`](docs/04_data_dictionary.md) | The four exported marts, column by column |
| [`docs/05_traceability_matrix.md`](docs/05_traceability_matrix.md) | Every BR to model, test and dashboard element; dbt tests stand in for UAT |
| [`docs/FINDINGS.md`](docs/FINDINGS.md) | Where the code contradicted a baselined doc |
| `PROJECT_BRIEF.md`, `docs/01_project_charter.md`, `docs/02_brd.md` | Baselined, superseded where the code differs |
| `docs/verification/` | Verification-phase findings, historical |

## Not built

Disclosed rather than built:

- FRD (`docs/03`) and a standalone UAT plan (`docs/06`, folded into the
  traceability matrix, where dbt tests are the evidence).
- Event study of chokepoint traffic around a disruption (D-7, BR-14).
  PortWatch daily transits are loaded and staged for it; no mart reads
  them.
- Excel scenario workbook (D-10, BR-23).
- Scheduled refresh via GitHub Actions (BR-27). Refresh is manual.
- PortWatch data-quality dbt tests (blackout dates, signal loss, series
  breaks). They govern the transits, which feed nothing yet.
- A dbt test for value continuity across the 2021/2022 HS break (BR-13).
  The check was run by query (`docs/07` §6.2).

## What this cannot support

- **Exposure is not a measured route.** It is the share of value whose
  shortest sea path passes near a chokepoint. Carrier routing, Cape
  diversions since late 2023, transshipment and goods trucked in from
  Mexican or Canadian ports are not modelled.
- **Air freight is not routed.** Most semiconductor value flies, so a
  near-zero exposure for a chip code is a finding, not a gap.
- **Supplier is country of origin**, not fab or mine. A spread of origin
  countries can sit on one upstream supplier.
- **Port weights are one PortWatch snapshot** applied to every year from
  2018.
- **Coast shares are per code**, not per supplier country.
- **HS2022 successors share family-level concentration.** All four
  854140 successors show the family HHI and suppliers, so the solar
  module points show Indonesia as top supplier for the whole family.
- **No price, tariff or capacity data**, and no forecasting.

## How this was built

Implementation with Claude Code; scoping, requirements and verification
by me.
