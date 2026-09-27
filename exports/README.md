# exports

The four CSVs the Tableau dashboard reads, one per mart, written by `make export` (`ingest/export.py`) after `make dbt-build`. Committed so the dashboard can be rebuilt without running the pipeline.

- `fct_exposure_summary.csv`: one row per HS6 code, year, weighting and coast; the 2x2.
- `fct_supplier_share.csv`: supplier countries and shares per product and year.
- `fct_concentration.csv`: HHI and top supplier per product and year.
- `fct_exposure.csv`: exposure per code, year, chokepoint, distance, weighting and coast. Columns: [`docs/04_data_dictionary.md`](../docs/04_data_dictionary.md).
