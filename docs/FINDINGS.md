# Findings

Build-phase findings where the code contradicts a baselined doc or a documented assumption turns out wrong. See CLAUDE.md's FINDINGS protocol.

- 2026-09-19 Census cache is annual, not monthly. Brief section 4 and
  CLAUDE.md say monthly. Annual is correct for DR-9 and is what the cache
  holds. Code wins.
- 2026-09-19 hs_version is not present in the Census API response and can
  only be derived from the year. CLAUDE.md says carry hs_version through
  raw. Raw stays faithful to source, derivation moves to stg_census.
  Code wins.
- 2026-09-19 28 census_hs_annual files but only 20 census_porths_vessel
  files. 8 codes have mode shares but no coast share, so routing_weight
  cannot be computed for them. Affects BR-07. Unresolved, codes not yet
  identified.
- 2026-09-19 Correction to the previous entry. Cache holds
  census_porths_vessel for all 28 codes, not 20. No coast share gap.
  BR-07 unblocked.
- 2026-09-19 PortWatch blackout dates are present as rows with mostly
  nonzero counts, not absent and not zeroed. Exclusion belongs in the
  clean mart, and the dbt test asserts zero rows there, not in raw.
- 2026-09-19 Census SUMMARY_LVL CGP rows (36,621) confirmed present
  alongside DET (93,385), and the '-' sentinel (2,304 rows) is tagged
  DET. Staging must filter on both conditions.
