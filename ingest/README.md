# ingest

Python for the steps SQL can't do: calling APIs, reading Excel and computing sea routes. Every calculation on tables happens in dbt.

- `comtrade.py`, `census.py`, `portwatch.py`: pull each source into `data/raw/`, cache-first, failing loudly on any error.
- `hs_bridge.py`: builds the HS2017 to HS2022 product bridge. `routing.py`: routes every container port to three US ports and measures distance to 28 chokepoints.
- `load.py`: loads `data/raw/` into Postgres. `export.py`: writes the marts to `exports/`.
- `config.py`: every source URL, the year range, and secrets read from the environment. Each script has a `make` target.
