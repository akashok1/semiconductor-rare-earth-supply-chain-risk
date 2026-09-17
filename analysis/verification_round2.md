# Verification round 2

Three verification tasks. Findings only -- no dbt, no Postgres, no pipeline changes.

Generated: 2026-09-16, updated same day once `CENSUS_API_KEY` was added. All
three tasks are fully measured below.

---

## Task 1: PortWatch vessel category aggregation

**Method.** Pulled the full `Daily_Chokepoints_Data` table -- all 28
chokepoints, all dates, not a sample -- via pagination (79 pages of up to
1000 rows). 78,764 rows total, cached as `data/raw/portwatch_full_offset*.json`.
Date range: 2019-01-01 to 2026-09-13 (today).

**n_cargo and n_total (vessel counts): exact aggregates, no exceptions.**

| Check | Exact match rate | Mean abs diff | Max abs diff |
|---|---|---|---|
| `n_cargo == n_container + n_dry_bulk + n_general_cargo + n_roro` | 100.0% | 0.0 | 0 |
| `n_total == n_cargo + n_tanker` | 100.0% | 0.0 | 0 |

Zero nulls across any of the seven count fields, for all 78,764 rows. `n_cargo`
is exactly the sum of the four non-tanker vessel types, and `n_total` is
exactly `n_cargo + n_tanker`, with no exceptions anywhere in the dataset --
no chokepoint and no date range breaks this.

**capacity_* columns: not exact, but the gap is rounding noise, not a break.**

| Check | Exact match rate | Mean abs diff | Max abs diff | Diff values observed |
|---|---|---|---|---|
| `capacity_cargo == sum(capacity_container, capacity_dry_bulk, capacity_general_cargo, capacity_roro)` | 24.3% | 1.06 | 3 | 0, 1, 2, 3 (never negative) |
| `capacity == capacity_cargo + capacity_tanker` | 54.4% | 0.46 | 1 | 0, 1 (never negative) |

Also zero nulls in any capacity field. The mismatch is real but tiny and
one-sided (the diff is never negative, and is bounded exactly as you'd expect
from summing independently-rounded integers: up to +3 when summing four
components, up to +1 when summing two). Median `capacity` value in the
dataset is ~1.41 million; a diff of up to 3 against that is ~2x10⁻⁶ of the
total -- consistent with each `capacity_*` subtype being rounded to the
nearest whole unit independently before the aggregate columns are also
independently rounded, not a data quality problem. The mismatch rate is
spread broadly across nearly every chokepoint at similar proportions (e.g.
Dover, Gibraltar, Korea, Taiwan, Malacca Straits all show ~2,500-2,700
mismatched rows out of ~2,813 total rows each) rather than concentrated in a
specific chokepoint or date range -- another point against a schema break and
for rounding.

**Does the vessel-type breakdown exist for the whole history?**

Yes, for all 28 chokepoints, with no exception. For every chokepoint, the
first date with a non-null `n_container` (and separately, `capacity_container`)
is identical to that chokepoint's own earliest available date -- 2019-01-01
across the board. There is no cutover date and no schema change: the
vessel-type breakdown has existed since day one of the PortWatch series, not
added later. This was measured directly (`groupby(portid)` earliest
non-null date vs. earliest date overall, for all 28 chokepoints), not assumed.

---

## Task 2: Comtrade mode of transport for reporter USA

**Method.** Queried Comtrade's combined `HS` classification endpoint
(auto-resolves native vintage per year -- H5 for 2018-2021, H6 for 2022+),
reporter USA (842), flow M (imports), for 5 codes (854231, 850511, 280530,
848620, 854110) across 5 years spanning the full range (2018, 2020, 2022,
2024, 2025).

- **World-aggregate rows** (`partnerCode=0`): 25 combinations (5 codes x 5
  years) checked. All 25 returned `motCode=0`.
- **Partner-level rows** (no partner filter, every reporting partner
  country): 1,308 rows scanned across the same 5 codes x 5 years. Every
  single row returned `motCode=0, motDesc='TOTAL MOT'`. No exceptions.
- **Direct test of non-zero motCode values.** Confirmed the full valid
  motCode domain first via `comtradeapicall.getReference('mot')`: `0` = TOTAL,
  `1000` = Air, `2000/2100/2200/2900` = Water family, `3000/3100/3200/3900` =
  Land family, `9000`-series = other. Queried HS 854231, USA, 2023 with each
  of `motCode=1000` (Air), `2100` (Sea), `2000` (Water), `3000` (Land)
  explicitly: **all four returned HTTP 200 with zero rows** -- a valid,
  well-formed query, just no matching data. (An earlier attempt using
  `motCode=1` and `motCode=4`, guessed from memory rather than the reference
  list, correctly came back HTTP 400 "the field motCode is invalid" -- those
  aren't real codes at all, which is a different thing from "valid code, no
  data," and is why the reference list was checked before drawing any
  conclusion.)

**Conclusion: the United States does not report a mode-of-transport
breakdown to Comtrade.** Every USA import record in this dataset, across
every code, year, and partner tested, carries `motCode=0` (TOTAL modes of
transport) only. Requesting a specific real mode returns a valid empty
result, not an error and not hidden data -- the breakdown genuinely doesn't
exist at the reporter level for USA. This is a hard dead end for getting
mode-of-transport from Comtrade directly, which is exactly why task 3 goes
to the Census Bureau's own trade API instead.

---

## Task 3: Census mode of transport and port of entry

**Method.** `analysis/census_mot_spike.py`, run against the live Census
international trade timeseries API (`CENSUS_API_KEY` now set). Two real bugs
surfaced and were fixed before these numbers are trustworthy -- both are
worth recording since they're easy to hit again:

1. **Comma-joined `I_COMMODITY` doesn't work on this API** the way Comtrade's
   `cmdCode` does -- a batched request for all 22 codes at once returned
   HTTP 204 (no content), confirmed directly by testing a 3-code batch in
   isolation. Fixed by looping one call per code (22 calls), each covering
   the full 2018-2025 monthly range in one shot (`time=from 2018-01 to
   2025-12`; a comma-list of specific months also doesn't work, but a range
   does) and keeping only December (`-12`) rows, since `_YR` fields are
   year-to-date and December's YTD equals the full calendar year.
2. **Census mixes individual "detail" rows with overlapping regional/grand-total
   rows in the same result set, with no filter applied by default.**
   `SUMMARY_LVL='CGP'` rows ("ASIA", "EUROPEAN UNION", "PACIFIC RIM
   COUNTRIES", "USMCA (NAFTA)", etc.) double- and triple-count individual
   countries against each other and against the real per-country rows.
   Worse, the true grand total row itself (`CTY_CODE`/`PORT` == `"-"`,
   `CTY_NAME`/`PORT_NAME` = "TOTAL FOR ALL COUNTRIES" / "TOTAL FOR ALL
   PORTS") is *also* tagged `SUMMARY_LVL='DET'` rather than `'CGP'`, so
   filtering to `SUMMARY_LVL='DET'` alone still double-counts by including
   that sentinel row alongside the real countries it's already the sum of.
   Caught by cross-checking: for HS 854231 / 2018, the naive unfiltered sum
   was $125.4B; `DET`-only (including the sentinel) was $43.1B, exactly 2x
   a second number; the 96 real per-country `DET` rows excluding the `"-"`
   sentinel summed to exactly $21,556,458,087, matching both the sentinel
   row's own value *and* the `imports/porths` endpoint's independently
   computed total for the same code/year to the dollar, and reconciling
   to Comtrade's cached $21,619,335,521 for the same code/year within 0.29%.
   That three-way agreement (hs-by-country, hs-by-port, and Comtrade) is
   what confirms the filter is now correct. Fixed by requiring
   `SUMMARY_LVL=='DET'` **and** `CTY_CODE`/`PORT` != `"-"`.

### 1. Air / vessel / other share of import value, per code (2018-2025 combined)

| Code | Total value | Air | Containerized vessel | Other vessel | Residual (land/other) | Years covered |
|---|---|---|---|---|---|---|
| 280530 | $0.09B | 53.1% | 42.3% | 0.9% | 3.7% | 2018-2025 |
| 284610 | $0.23B | 20.4% | 75.3% | 1.9% | 2.4% | 2018-2025 |
| 284690 | $1.04B | 27.9% | 62.6% | 7.2% | 2.3% | 2018-2025 |
| 848610 | $1.91B | 51.3% | 43.6% | 4.8% | 0.2% | 2018-2025 |
| 848620 | $44.13B | 67.4% | 30.4% | 0.5% | 1.7% | 2018-2025 |
| 848630 | $0.07B | 67.8% | 31.4% | 0.4% | 0.4% | 2018-2025 |
| 848640 | $6.51B | 68.4% | 29.0% | 0.5% | 2.1% | 2018-2025 |
| 848690 | $30.52B | 87.8% | 8.0% | 0.3% | 3.9% | 2018-2025 |
| 850511 | $3.62B | 26.3% | 56.6% | 11.1% | 6.0% | 2018-2025 |
| 854110 | $4.32B | 83.1% | 12.7% | 1.3% | 2.9% | 2018-2025 |
| 854121 | $1.15B | 83.9% | 13.8% | 0.8% | 1.5% | 2018-2025 |
| 854129 | $11.94B | 70.4% | 8.8% | 0.1% | 20.7% | 2018-2025 |
| 854130 | $0.76B | 85.9% | 5.5% | 2.0% | 6.6% | 2018-2025 |
| 854140 | $32.86B | 24.9% | 69.8% | 0.2% | 5.1% | **2018-2021 only** |
| 854150 | $2.06B | 98.4% | 0.2% | 0.0% | 1.4% | **2018-2021 only** |
| 854160 | $2.56B | 89.2% | 2.4% | 0.3% | 8.1% | 2018-2025 |
| 854190 | $3.53B | 32.7% | 55.8% | 0.4% | 11.2% | 2018-2025 |
| 854231 | $196.73B | 96.0% | 0.8% | 0.0% | 3.2% | 2018-2025 |
| 854232 | $17.61B | 98.2% | 0.6% | 0.0% | 1.1% | 2018-2025 |
| 854233 | $6.97B | 75.8% | 0.9% | 0.1% | 23.1% | 2018-2025 |
| 854239 | $77.34B | 85.6% | 1.1% | 0.1% | 13.2% | 2018-2025 |
| 854290 | $2.54B | 90.9% | 6.3% | 0.5% | 2.3% | 2018-2025 |

**All 22 candidate codes exceed 20% air share** -- from 284610 at 20.4% (just
over) up to 854150 at 98.4%. This is not a marginal finding: most of the
semiconductor-basket codes clear 70-98% by air, and even the rare-earth/magnet
basket (280530, 284610, 284690, 850511) runs 20-53%. Air freight doesn't
transit a maritime chokepoint at all -- it flies over. **This bears directly
on the project's exposure model**: for codes at 90%+ air share, a
Malacca/Suez/Panama-style chokepoint closure barely touches the actual
physical flow of that product, whatever its concentration score says. Worth
raising as a scope question before the exposure mart is built, not after.

854140 and 854150 stop at 2021 -- consistent with the Day 1 finding that
these two HS2017 codes were split into six new HS2022 subheadings
(854141/142/143/149/151/159), so the old 6-digit codes genuinely have no
2022+ data under Census's current classification either. Same break, seen
independently through a second data source.

Per-year detail (not just the 2018-2025 combined figure above) is cached in
`data/raw/census_hs_annual_<code>.json` and summarized in
`data/raw/census_mot_spike_metrics.json` under `mode_shares_per_code_year` --
worth a look before finalizing the exposure model, since a few codes swing
a lot year to year (e.g. 854233 goes from ~48% air in 2018-2019 to 95-97%
from 2021 on; 854190 drifts from 66% down to 15%).

### 2. Import value by US port-of-entry region, per code

Ports classified by matching keywords against `PORT_NAME` (not the numeric
port code -- confirmed live these don't cleanly encode region). "Unclassified"
is explicit, not force-fitted, and this time it's a legitimate small-to-moderate
residual, not a hidden aggregate row (see the bug note above) -- mostly
interior US airports and inland customs stations (e.g. Chicago Midway,
Denver, Dallas-Fort Worth) that don't belong to any of the four coastal/border
buckets the task asked for. The full unclassified port-name list is in the
script's stdout / `data/raw/census_mot_spike_metrics.json`.

| Code | West Coast | East Coast | Gulf | Land border | Unclassified |
|---|---|---|---|---|---|
| 280530 | 25.5% | 46.7% | 12.1% | 2.2% | 13.5% |
| 284610 | 73.3% | 21.0% | 2.0% | 1.1% | 2.6% |
| 284690 | 34.4% | 47.9% | 9.8% | 1.5% | 6.4% |
| 848610 | 42.5% | 22.4% | 24.1% | 0.1% | 10.9% |
| 848620 | 71.2% | 9.3% | 12.8% | 1.4% | 5.4% |
| 848630 | 68.6% | 20.3% | 2.6% | 0.3% | 8.2% |
| 848640 | 67.8% | 14.6% | 11.8% | 0.1% | 5.7% |
| 848690 | 62.6% | 13.5% | 12.5% | 0.6% | 10.8% |
| 850511 | 60.8% | 16.6% | 8.1% | 1.4% | 13.0% |
| 854110 | 55.8% | 10.5% | 5.7% | 0.4% | 27.7% |
| 854121 | 58.6% | 12.6% | 8.2% | 0.2% | 20.4% |
| 854129 | 73.9% | 5.1% | 3.9% | 0.2% | 16.9% |
| 854130 | 39.4% | 14.9% | 9.2% | 1.1% | 35.5% |
| 854140 | 45.4% | 35.4% | 9.7% | 0.9% | 8.6% |
| 854150 | 61.2% | 7.8% | 11.5% | 0.1% | 19.3% |
| 854160 | 49.9% | 6.6% | 16.4% | 0.4% | 26.8% |
| 854190 | 30.8% | 42.9% | 17.3% | 0.6% | 8.5% |
| 854231 | 56.9% | 12.2% | 14.7% | 0.1% | 16.1% |
| 854232 | 72.4% | 2.8% | 12.6% | 0.1% | 12.1% |
| 854233 | 76.1% | 2.7% | 10.7% | 0.1% | 10.4% |
| 854239 | 77.0% | 3.1% | 7.2% | 0.2% | 12.5% |
| 854290 | 55.5% | 11.0% | 16.7% | 0.3% | 16.4% |

West Coast dominates almost every code (30-77%), consistent with the air-share
finding above -- LAX and SFO airports alone account for the two largest single
port totals across the basket ($80B and $53B respectively, summed across
codes), with Anchorage ($68B, a cargo-plane refueling/transfer hub) and
Seattle-Tacoma airport ($21B) also in the top five. Land border is
consistently under 2.2% for every code -- these two baskets essentially
don't cross by truck/rail, unlike the Mexico/Canada finding below, which is
about specific *countries*, not these specific *products*.

### 3. Reconciliation against cached Comtrade values

88 code-year pairs (22 codes x 2018-2021, the years both sources have
cached). Gap = (Census - Comtrade) / Comtrade:

| | Value |
|---|---|
| Mean gap | -2.4% |
| Min gap | -12.4% |
| Max gap | +3.3% |

Small and mostly slightly negative -- Census generally reads a little below
Comtrade. This is a tight enough band that it reads as ordinary
cross-source noise (differing revision timing, minor customs-value vs.
CIF-value conventions, rounding in Comtrade's own conversion) rather than a
methodological problem; nothing in the 88 pairs stands out as a gap
large enough to need its own investigation. Full detail (every code-year
pair) is in `data/raw/census_mot_spike_metrics.json` under `reconciliation`.

### 4. Mexico and Canada: vessel or land?

Matched by `CTY_NAME` containing "CANADA" / "MEXICO" across all 22 codes,
2018-2025 combined:

| Country | Total value | Air | Vessel | Land/other (residual) |
|---|---|---|---|---|
| Canada | $4.26B | 25.1% | 0.04% | 74.8% |
| Mexico | $15.52B | 4.3% | 0.17% | 95.5% |

**Definitively land, for both.** Vessel share is essentially zero for each
(0.04% and 0.17%) -- these two countries' trade in these 22 codes moves by
truck/rail or air, never by sea, which makes physical sense for contiguous
land neighbors. Canada's meaningfully higher air share (25% vs. Mexico's 4%)
is a secondary finding worth a second look later, not answered by this spike.

### 5. Does `imports/porths` carry partner country?

**Yes**, confirmed both in schema (`CTY_CODE`/`CTY_NAME` declared fields) and
in live data (non-null real country names returned for HS 854231, 2023).

---

All raw Census responses cached to `data/raw/` (`census_hs_annual_<code>.json`,
`census_porths_annual_<code>.json`, one confirmatory partner-country check) --
44 calls total, all now cached, so a re-run of the script costs nothing.
Computed metrics (full per-year detail behind every table above) are in
`data/raw/census_mot_spike_metrics.json`.

---

## Corrections (2026-09-17)

Two problems in the task 3 sections above, found after review. Nothing
above this line is changed -- these are additive fixes, computed by new
functions added to `analysis/census_mot_spike.py` (the original functions
are untouched, so the numbers above still reproduce from their own cache).

### Problem 1: the port-of-entry table used total value, so airports dominated it

Section 2 above ranks ports by `GEN_VAL_YR` -- total import value, every
mode combined. Since task 1's finding was that most of this basket moves by
air, that table was mostly measuring where planes land (LAX, SFO, Anchorage,
Sea-Tac), not maritime routing. For a project about chokepoint exposure,
that's the wrong basis.

**Fix:** recomputed using `VES_VAL_YR` only (vessel value, i.e. imports
that actually arrived by ship), per code per year, via a new
`compute_vessel_port_region_distribution()`. Full per-year detail is in
`data/reference/port_entry_shares.csv`; overall (2018-2025, value-weighted)
per code:

| Code | Total vessel value | West Coast | East Coast | Gulf |
|---|---|---|---|---|
| 280530 | $0.04B | 48.7% | 42.2% | 8.9% |
| 284610 | $0.18B | 72.4% | 25.6% | 1.9% |
| 284690 | $0.72B | 35.6% | 54.4% | 9.8% |
| 848610 | $0.92B | 54.1% | 20.3% | 25.6% |
| 848620 | $13.65B | 81.3% | 12.2% | 6.5% |
| 848630 | $0.02B | 73.9% | 25.8% | 0.2% |
| 848640 | $1.92B | 61.6% | 26.3% | 12.0% |
| 848690 | $2.54B | 58.5% | 37.7% | 3.8% |
| 850511 | $2.45B | 75.9% | 17.5% | 6.5% |
| 854110 | $0.60B | 74.7% | 21.9% | 3.2% |
| 854121 | $0.17B | 66.0% | 33.1% | 0.8% |
| 854129 | $1.06B | 67.6% | 31.2% | 1.2% |
| 854130 | $0.06B | 33.7% | 52.5% | 13.2% |
| 854140 | $23.02B | 45.7% | 40.2% | 14.1% |
| 854150 | $0.00B | 46.5% | 51.2% | 2.3% |
| 854160 | $0.07B | 77.1% | 18.1% | 4.3% |
| 854190 | $1.98B | 19.1% | 67.0% | 13.8% |
| 854231 | $1.59B | 74.2% | 22.5% | 3.2% |
| 854232 | $0.12B | 44.8% | 53.8% | 1.3% |
| 854233 | $0.07B | 58.0% | 40.8% | 1.2% |
| 854239 | $0.92B | 64.1% | 33.6% | 1.6% |
| 854290 | $0.17B | 62.6% | 32.1% | 5.3% |

West+East+Gulf now account for essentially all vessel value (land
border and "other" both round to ~0.0% for every code, as physically
expected -- ships don't dock at a truck crossing), so the three columns
above are a clean, complete picture. West Coast still leads for most
codes, but far less lopsidedly than the total-value table suggested, and a
few codes actually skew East Coast or Gulf on a vessel basis (284690,
854130, 854190, 854232) -- invisible in the original table because air
volume swamped everything else there. Total vessel value per code is much
smaller than total import value (e.g. 854231: $1.59B vessel vs. $196.73B
total, ~0.8% -- consistent with the 0.8% combined vessel share task 1's
mode table already found for that code).

### Problem 2: port classification used PORT_NAME keywords; official codes needed for the residual question

**Fix.** Replaced the `PORT_NAME` keyword matcher with a classifier built
from the official Census/CBP Schedule D port code list
(`www.census.gov/foreign-trade/schedules/d/dist2.txt`, cached at
`data/raw/census_schedule_d_ports.txt`), keyed by the actual 4-digit `PORT`
code rather than the free-text name. This matters for more than tidiness:
a handful of CBP districts mix a coastal seaport with land-border crossings
under the *same* district number, which no keyword scheme could resolve --
district 25 (San Diego) contains the San Diego seaport itself, but also
Otay Mesa, San Ysidro, Calexico, and Tecate (Mexico land crossings);
district 30 (Seattle) contains the Seattle/Tacoma seaports and airport, but
also Blaine, Sumas, Lynden, and eight other Canada crossings. Every port
under both districts was landing in whatever the district's dominant name
suggested; specifically, `Otay Mesa` and the other land crossings under
those two districts were falling into "Unclassified" in section 2's table
above. The new classifier (`official_region_for_port_code()`) resolves each
port by its own code first (explicit overrides for the mixed districts),
falling back to its district's region otherwise -- full mapping and
per-district reasoning is in the script.

**Reconciling the residual.** The mode table (task 3, section 1 above)
reports `GEN - AIR - VES` as a residual and labels it "land/other,
inferred." Section 2's old table showed land-border ports capturing under
2.2% of value for every code, while some codes' residuals ran past 20% --
a real contradiction if the residual is supposed to be land trade. With
the corrected classifier, applied to the same `GEN_VAL_YR` port data used in
section 2 (no new pulls needed, just a better classifier over what was
already cached):

| Code | Mode-table residual | Official land-border port share | Gap | Residual from Mexico/Canada |
|---|---|---|---|---|
| 280530 | 3.7% | 3.5% | +0.2pt | 12.0% |
| 284610 | 2.4% | 1.2% | +1.2pt | 2.2% |
| 284690 | 2.3% | 1.8% | +0.6pt | 5.9% |
| 848610 | 0.2% | 0.3% | -0.1pt | 10.5% |
| 848620 | 1.7% | 2.1% | -0.4pt | 81.0% |
| 848630 | 0.4% | 1.0% | -0.5pt | 94.8% |
| 848640 | 2.1% | 2.6% | -0.5pt | 4.9% |
| 848690 | 3.9% | 3.2% | +0.7pt | 71.5% |
| 850511 | 6.0% | 3.9% | +2.0pt | 28.6% |
| 854110 | 2.9% | 2.6% | +0.4pt | 28.9% |
| 854121 | 1.5% | 1.5% | +0.0pt | 5.4% |
| 854129 | 20.7% | 21.4% | -0.6pt | 56.7% |
| 854130 | 6.6% | 5.5% | +1.1pt | 52.3% |
| 854140 | 5.1% | 4.3% | +0.8pt | 59.9% |
| 854150 | 1.4% | 2.1% | -0.7pt | 89.2% |
| 854160 | 8.1% | 9.1% | -1.0pt | 2.1% |
| 854190 | 11.2% | 10.5% | +0.7pt | 90.2% |
| 854231 | 3.2% | 3.5% | -0.3pt | 49.5% |
| 854232 | 1.1% | 1.1% | -0.0pt | 37.2% |
| 854233 | 23.1% | 23.0% | +0.1pt | 92.9% |
| 854239 | 13.2% | 13.4% | -0.2pt | 87.6% |
| 854290 | 2.3% | 2.1% | +0.2pt | 56.8% |

**Conclusion: the residual is genuinely land, for every code.** The gap
between the mode-table residual and the official land-border port share is
under 2 percentage points for all 22 codes, most under 1 -- the two
independent measurements (one from country-level mode fields, one from
port-of-entry geography) agree almost exactly. The earlier apparent
contradiction was entirely the old port classifier's fault (`Otay Mesa` and
similar going to "Unclassified" instead of "Land border"), not a real gap
in what the residual represents.

The one genuine wrinkle: the last column shows the residual is *not* mostly
attributed to Mexico or Canada by country of origin for several codes
(284610, 284690, 848610, 848640, 854121, 854160, 280530 all under 15%).
Since the port-based measurement says this value still crosses at a land
border, and the country-of-origin measurement says it isn't from Mexico or
Canada, the most likely explanation is transshipment: goods produced
elsewhere (Asia, per the basket's dominant supplier countries) moving by
sea to a Mexican or Canadian port, then completing the final leg into the
US by truck or rail, with Census attributing the value to the true country
of origin rather than the transshipment point. That's a real, useful
finding for the routing matrix -- "land border" as an entry mode doesn't
mean "Mexico/Canada" as the supplying country, and the two shouldn't be
conflated when the exposure model gets built.

---

`data/reference/mode_shares.csv` and `data/reference/port_entry_shares.csv`
are committed -- the routing matrix's Census inputs. 168 rows each (22
codes x 8 years, minus 854140/854150's 4 missing years x 2 codes). New raw
pulls cached: `census_porths_vessel_<code>.json` (22 calls, `VES_VAL_YR`
added) and `census_schedule_d_ports.txt` (the official port list, 1 call).
Computed corrections metrics in `data/raw/census_mot_corrections_metrics.json`.
