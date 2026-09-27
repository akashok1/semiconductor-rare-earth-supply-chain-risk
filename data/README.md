# data

- `raw/`: every API response, cached on first pull and never edited. Gitignored; `make all` rebuilds it, and a rerun costs zero API calls.
- `reference/manual/`: decisions a person owns, one reason per row: basket HS codes, bridge overrides, Census district to coast map, landlocked gateways, US destination ports, the chokepoint risk set.
- `reference/generated/`: written only by `ingest/` scripts: the HS bridge, Census port and country lists, sea routes and the routing matrix.
- `reference/fixtures/`: expected values kept for testing.
- dbt loads everything under `reference/` as seed tables (`make dbt-build`).
