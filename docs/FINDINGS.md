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

- 2026-09-22 17:25 Census _YR columns are year-to-date cumulative reported
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

- 2026-09-22 routing_matrix has no Gulf destination; Gulf vessel share (up to 45.9 percent for 854130 in 2025) has no route and reads as zero exposure. Brief and CLAUDE.md describe coast share as fully routed. Code wins until Houston is added.
- 2026-09-22 census_porths_vessel was pulled without CTY_CODE, so coast share exists per code only, not per country. Supersedes the earlier suggestion of a per-country port_coast_map seed. Code wins.
- 2026-09-22 Census raw data and 2018-2021 Comtrade were pulled by analysis/ scripts, not ingest/. CLAUDE.md lists ingest/census.py and ingest/portwatch.py as the ingest layer. Code wins, README runbook must say so.

- 2026-09-23 01:15 mode_shares.csv, port_entry_shares.csv and
  basket_selection.csv have no generating script in the repo. The two
  share CSVs predate all retained session transcripts; basket_selection
  was written by an inline heredoc (2026-09-18 23:08 UTC). CLAUDE.md
  and verification_round2.md imply census_mot_spike.py produced them;
  it covers 22 codes and writes no CSV. Code wins: unreproducible until
  dbt recomputes the shares and basket codes become a manual CSV.
- 2026-09-23 01:15 PortWatch daily transit cache (78,764 rows, pulled
  2026-09-16) has no surviving fetch code; it predates all retained
  transcripts. Census caches for the six HS2022 successor codes were
  pulled by uncommitted scratch scripts (fetch_854151_854159.py,
  2026-09-18 22:47 UTC). Code wins: portwatch.py and census.py rebuild
  both against the existing cache.
- 2026-09-23 01:15 CLAUDE.md scoped out the PortWatch ports database as
  "the 2,065-port dataset." Port coordinates move to it from the
  improved-un-locodes GitHub republication. The scope line covered port
  traffic analysis, not coordinates. Refactor wins.
- 2026-09-23 01:15 census_porths_annual covers 22 codes, none of the six
  HS2022 successors, and has no staging model. Exploration only.
  Dropped from ingest and load.
- 2026-09-23 01:15 census_schedule_d_ports.txt is cached but never read;
  the port classifier's district dicts were hand-copied from it. Wired
  in as the source for the district to coast map in the refactor.
- 2026-09-23 01:15 CLAUDE.md exposure formula used Comtrade partner
  share times code-level containerized share, assigning maritime
  exposure to land-dominant partners. Replaced with Census country-level
  containerized value. CLAUDE.md updated. Refactor wins.
- - 2026-09-23 01:31 CLAUDE.md said Comtrade world totals were verified
  "within 0.68 percent of the reported World row." Raw checks show
  partner 0 equals the sum of partner rows exactly; 0.68% was the Census
  vs Comtrade gap for 854231 2023. CLAUDE.md corrected. Data wins.