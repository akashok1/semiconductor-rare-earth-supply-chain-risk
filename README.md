# Import Concentration Risk

How concentrated is the US supply of a given import, and how exposed is that
supply to a maritime chokepoint closure? Built around one decision: ahead of
annual supplier contract renewals, where should a mid-size US electronics
manufacturer qualify a second supplier, and where should it hold buffer
inventory?

Concentration is measured (from UN Comtrade bilateral trade data). Exposure
is modelled (a routing assumption, not a direct measurement). The project
keeps that distinction explicit everywhere it shows up.

**Dashboard:** _link pending_
**Screenshots:** _pending_

## The two baskets

- **Semiconductors and semiconductor manufacturing equipment** (HS 8541,
  8542, 8486 families): matches the analyst's referral network and the
  SEMICON West conference circuit, a basket with real domain context behind it.
- **Rare earths and permanent magnets** (HS 2805.30, 2846 family, 8505.11):
  gives the most portable, legible concentration story of the candidate
  baskets considered (pharma APIs and advanced packaging substrates were the
  alternatives).

Both were chosen over broader alternatives specifically because a 5-day build
window doesn't support a wide product scope. Full reasoning and rejected
alternatives are in `PROJECT_BRIEF.md` section 14.

## Headline findings

**Concentration doesn't move the way the brief expected.** The working
hypothesis was that China's downstream magnet manufacturing (HS 850511) would
be more concentrated than its raw rare-earth metal supply (HS 280530). Measured
2023 Comtrade data shows the opposite: raw rare-earth metals are the single
most concentrated product in either basket (HHI 9,749, 12 suppliers, China at
98.7%), more concentrated than the downstream magnets (HHI 6,413, 55
suppliers, China at 79.8%). Semiconductors sit far below both: integrated
circuit codes run HHI 1,500-2,200 across 40-90 suppliers, spread across
Malaysia, Korea, Japan, China, and Taiwan. The magnet/raw-metal comparison
was worth measuring precisely because it could have gone either way.

**Almost all of this trade arrives by air, not by sea.** Every one of the 22
candidate HS6 codes exceeds 20% air share of import value; several
semiconductor codes run 90%+ (854150 at 98.4%, 854231 at 96.0%, 854232 at
98.2%). Comtrade doesn't report a mode-of-transport breakdown for US imports
at all (confirmed directly: querying any real, non-zero mode code returns a
valid, empty result), so this came from the Census Bureau's own international
trade API instead. This matters for the project's core premise: a maritime
chokepoint closure has limited bearing on a product that mostly moves by
plane. See `docs/verification/02_mode_and_port_of_entry.md` task 3 for the full breakdown,
per code and per year.

Full findings, including the PortWatch data-quality checks and the searoute
chokepoint-crossing spike, are in `docs/verification/01_sources_and_hs_codes.md`,
`docs/verification/02_mode_and_port_of_entry.md`, and `docs/verification/03_routing_method.md`.

## Method

- HS6 codes and classification vintage verified against Comtrade's live
  reference list before use, not assumed from memory or from the brief's
  candidate list.
- Concentration (HHI, top-supplier share) computed from Comtrade partner-level
  import data, with the `World` aggregate row explicitly excluded (left in,
  every share is wrong by roughly half).
- Mode of transport and US port of entry sourced from the Census Bureau's
  international trade API, since Comtrade carries no mode breakdown for US
  reporters; reconciled against Comtrade's own import values to within a few
  percent as a cross-check.
- Chokepoint exposure approximated by computing the shortest sea route
  (`searoute`) between origin and US destination ports, then checking which
  of IMF PortWatch's 28 chokepoints each route passes within 200km of.
- Every live API response is cached to `data/raw/` on first pull; every
  finding is reproducible from that cache without re-querying the source.

## Running it from a clean clone

Requires Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and free API keys
for [UN Comtrade](https://comtradeplus.un.org/) and the
[Census Bureau](https://api.census.gov/data/key_signup.html).

```bash
git clone https://github.com/akashok1/import-concentration-risk.git
cd import-concentration-risk
uv sync
cp .env.example .env
# edit .env: set COMTRADE_API_KEY and CENSUS_API_KEY
```

Start Postgres (Docker, port 5433), then run the pipeline in order with the
Makefile targets:

```bash
docker compose up -d
make bridge      # HS2017/HS2022 bridge, data/reference/generated/hs_bridge.csv
make comtrade    # UN Comtrade, US imports by partner, 2018-2025
make census      # Census imports by country and mode, vessel imports by port
make portwatch   # PortWatch chokepoints, daily transits, ports, disruptions
make routing     # sea routes, generated/routes.csv and routing_matrix.csv
make load        # data/raw and generated routing into Postgres raw.*
make dbt-build   # seeds, staging models and tests
```

`make all` runs the same sequence. Every ingest target is cache-first: API
responses cache under `data/raw/` on first pull, and a rerun with the cache
on disk costs zero calls. Pass flags through `ARGS`, e.g.
`make comtrade ARGS="--refresh 2025"` to re-pull one year. After a seed's
columns or types change, run `make dbt-seed-full` (`dbt seed
--full-refresh`) before `make dbt-build`. `make dbt-seed`, `make dbt-test`,
`make dbt-run`, `make dbt-debug` and `make dbt-docs` run the single dbt
command.

The two Jupyter notebooks under `notebooks/` (`01_first_look.ipynb` for
Comtrade, `02_portwatch_look.ipynb` for PortWatch) are exploratory scratchpads,
not part of the pipeline; open them with the `.venv` kernel to follow the same
exploration path interactively.

`data/reference/manual/` holds hand-owned decisions, each row with a reason.
`data/reference/generated/` is written only by `ingest/` scripts.
`data/reference/fixtures/mode_shares_expected.csv` is a verification-phase
test fixture, not a pipeline input. `data/raw/` is gitignored and rebuilds
from source on first run.

## What this cannot support

- **No live pipeline yet.** There is no dbt project, no Postgres landing
  schema, and no scheduled refresh. Everything here is a verification and
  measurement pass, not production infrastructure.
- **Concentration is a single snapshot (2023), not yet a full time series.**
  The 2018-2025 mart described in the project brief hasn't been built; what
  exists is per-code, per-year Comtrade pulls in the verification scripts.
- **Chokepoint exposure is a geometric proxy, not a measured route.** It
  checks proximity between a computed shortest sea route and a chokepoint's
  coordinates, measured as the true nearest point on the route line (not just
  its vertices), against a 200km threshold. A miss doesn't prove a route
  doesn't pass near a chokepoint.
- **Mode-of-transport and port-of-entry data won't reconcile exactly to
  Comtrade.** The two sources track a few percent apart (see
  `docs/verification/02_mode_and_port_of_entry.md` task 3), consistent with ordinary cross-source
  differences, not a resolved discrepancy.
- **No tier-2 or tier-3 supplier visibility.** Comtrade measures country of
  record, not ultimate producer. A concentration score can miss a shared
  upstream supplier sitting behind two "different" countries.
- **No price, tariff, or landed-cost modelling**, and no forecasting.
  The measures here describe current and historical exposure, not where it's
  headed or what it costs to fix.
