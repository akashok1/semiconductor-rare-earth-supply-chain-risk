# db

- `schema.sql`: creates the `raw` schema and its 10 tables in Postgres, one per source feed. Source columns are stored as text, exactly as received.
- Safe to rerun (it never drops anything). `make schema` applies it; `make all` runs it before `make load`.
- Raw tables are loaded once from `data/raw/` and never edited; dbt reads them and writes everything else.
