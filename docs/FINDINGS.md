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
- - 2026-09-22 17:25 Census _YR columns are year-to-date cumulative reported
  monthly, not annual. The 2026-09-19 entry calling the cache annual is
  wrong. Mode and coast shares must be taken from the December row per code
  per year, never summed across months. Code wins.
- 2026-09-22 17:00 Census _YR columns are year-to-date cumulative reported
  monthly. December holds the annual total. The 2026-09-19 entry calling
  the cache "annual" is imprecise and is superseded by this line. Summing
  across months inflates by ~6.2x. Verified: 854231 2023 December
  $20.14B against Comtrade World $20.28B, a 0.68 percent gap.
- 2026-09-22 17:00 census_mot_spike.py and both committed seeds already
  filter to December. All four headline figures reproduce independently
  within 0.03 points. No correction needed.
- 2026-09-22 17:00 mode_shares.csv and port_entry_shares.csv are 192 rows,
  28 codes x 8 years, including the HS2022 successors.
  verification_round2.md's 168 row figure predates the split codes.
- 2026-09-22 17:00 Mode shares will be computed in dbt from stg_census_hs
  rather than read from the seed. The seed becomes a test fixture asserting
  the pipeline reproduces the verified figures.
