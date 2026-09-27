# dbt

dbt turns the raw tables into the marts the dashboard reads, in SQL, and tests them. Run with `make dbt-build` (seeds, models and tests) or `make dbt-test`.

- `models/staging/`: one model per raw table: rename, cast, filter. No joins.
- `models/intermediate/`: mode and coast shares, port weights, route crossings.
- `models/marts/`: `fct_supplier_share`, `fct_concentration`, `fct_exposure`, `fct_exposure_summary`.
- `tests/`: 13 custom tests; with the `schema.yml` tests, 97 in total. `analyses/`: one-off SQL checks, never built.
