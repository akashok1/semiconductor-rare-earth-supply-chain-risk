# Verification round 1 findings

Generated: 2026-09-17T23:57:36+00:00
Source: `analysis/verification_round1.py`, run against live Comtrade and IMF PortWatch endpoints. Raw responses cached under `data/raw/`.

## 1. Candidate HS6 codes vs. the live HS2017 (H5) code list

### Semiconductors and semiconductor manufacturing equipment (`semiconductors_and_sme`)

- Heading `8541`: 8 HS6 leaf code(s) found
  - `854110`: 854110 - Electrical apparatus; diodes, other than photosensitive or light-emitting diodes (LED)
  - `854121`: 854121 - Electrical apparatus; transistors, (other than photosensitive), with a dissipation rate of less than 1W
  - `854129`: 854129 - Electrical apparatus; transistors, (other than photosensitive), with a dissipation rate of 1W or more
  - `854130`: 854130 - Electrical apparatus; thyristors, diacs and triacs, other than photosensitive devices
  - `854140`: 854140 - Electrical apparatus; photosensitive, including photovoltaic cells, whether or not assembled in modules or made up into panels, light-emitting diodes (LED)
  - `854150`: 854150 - Electrical apparatus; photosensitive semiconductor devices n.e.c. in heading no. 8541, including photovoltaic cells, whether or not assembled in modules or made up into panels
  - `854160`: 854160 - Crystals; mounted piezo-electric
  - `854190`: 854190 - Electrical apparatus; parts for diodes, transistors and similar semiconductor devices and photosensitive semiconductor devices
- Heading `8542`: 5 HS6 leaf code(s) found
  - `854231`: 854231 - Electronic integrated circuits; processors and controllers, whether or not combined with memories, converters, logic circuits, amplifiers, clock and timing circuits, or other circuits
  - `854232`: 854232 - Electronic integrated circuits; memories
  - `854233`: 854233 - Electronic integrated circuits; amplifiers
  - `854239`: 854239 - Electronic integrated circuits; n.e.c. in heading no. 8542
  - `854290`: 854290 - Parts of electronic integrated circuits
- Heading `8486`: 5 HS6 leaf code(s) found
  - `848610`: 848610 - Machines and apparatus of a kind used solely or principally for the manufacture of semiconductor boules or wafers
  - `848620`: 848620 - Machines and apparatus of a kind used solely or principally for the manufacture of semiconductor devices or of electronic integrated circuits
  - `848630`: 848630 - Machines and apparatus of a kind used solely or principally for the manufacture of flat panel displays
  - `848640`: 848640 - Machines and apparatus of a kind used solely or principally for the manufacture or repair of masks and reticles, assembling semiconductor devices or electronic integrated circuits, or for lifting, handling, loading or unloading items of heading 8486
  - `848690`: 848690 - Machines and apparatus of heading 8486; parts and accessories

### Rare earths and permanent magnets (`rare_earths_and_magnets`)

- Heading `2846`: 2 HS6 leaf code(s) found
  - `284610`: 284610 - Cerium compounds
  - `284690`: 284690 - Compounds, inorganic or organic (excluding cerium), of rare-earth metals, of yttrium, scandium or of mixtures of these metals
- Explicit code `280530`: **EXISTS**: 280530 - Earth-metals, rare; scandium and yttrium, whether or not intermixed or interalloyed
- Explicit code `850511`: **EXISTS**: 850511 - Magnets; permanent magnets and articles intended to become permanent magnets after magnetisation, of metal

All explicitly named codes from PROJECT_BRIEF.md section 3 exist in the live HS2017 (H5) list. Family headings resolved to the leaf codes above.

## 2. Latest available year for US import data

- Latest year available under **any** classification: **2025**
- Latest year still natively classified as HS2017 (H5): **2021** (H5-native years: [2017, 2018, 2019, 2020, 2021])

- Classification vintage by year (reporter USA): H0: 1991-1995, H1: 1996-2001, H2: 2002-2006, H3: 2007-2011, H4: 2012-2016, H5: 2017-2021, H6: 2022-2025

**Finding:** US import data under the project's chosen HS2017 (H5) classification runs through 2021 only. Years 2022-2025 are reported under a newer revision. Querying the H5-tagged endpoint for those later years returns zero rows rather than converted data. Comtrade does not silently reclassify. This is the HS concordance problem named in PROJECT_BRIEF.md section 6, arriving one revision earlier than the brief's stated backward-only H4 enhancement anticipated. Extending this project's year range past 2021 requires the bridge table, not a wider H5 query.

## 3. Import value and record count per surviving code, 2018-2021

Pulled for 2018-2021 only, the overlap between the brief's requested start year and the last year with native H5 data (see finding above). One batched Comtrade call per year covers every surviving code.

| Code | Basket | 2018 | 2019 | 2020 | 2021 | Total value (USD) | Flag |
|---|---|---|---|---|---|---|---|---|
| `280530` | rare_earths_and_magnets | $7,915,298 (8 rec) | $8,281,433 (8 rec) | $8,978,071 (10 rec) | $17,421,536 (10 rec) | $42,596,338 |  |
| `284610` | rare_earths_and_magnets | $42,219,958 (12 rec) | $41,511,611 (13 rec) | $31,509,105 (11 rec) | $32,058,893 (16 rec) | $147,299,567 |  |
| `284690` | rare_earths_and_magnets | $114,800,290 (22 rec) | $113,991,396 (20 rec) | $66,739,537 (19 rec) | $107,470,622 (20 rec) | $403,001,845 |  |
| `848610` | semiconductors_and_sme | $168,690,403 (23 rec) | $158,152,754 (20 rec) | $88,716,743 (18 rec) | $69,317,227 (24 rec) | $484,877,127 |  |
| `848620` | semiconductors_and_sme | $3,774,566,210 (42 rec) | $6,685,663,976 (41 rec) | $3,698,656,030 (38 rec) | $4,492,157,448 (42 rec) | $18,651,043,664 |  |
| `848630` | semiconductors_and_sme | $14,804,318 (15 rec) | $9,873,758 (10 rec) | $4,435,465 (16 rec) | $5,066,472 (18 rec) | $34,180,013 |  |
| `848640` | semiconductors_and_sme | $682,771,182 (33 rec) | $532,934,608 (33 rec) | $441,008,680 (32 rec) | $601,344,116 (35 rec) | $2,258,058,586 |  |
| `848690` | semiconductors_and_sme | $3,981,878,483 (72 rec) | $3,195,910,499 (68 rec) | $3,875,447,511 (61 rec) | $3,874,718,307 (67 rec) | $14,927,954,800 |  |
| `850511` | rare_earths_and_magnets | $406,265,003 (54 rec) | $392,530,217 (52 rec) | $331,268,320 (50 rec) | $508,377,634 (51 rec) | $1,638,441,174 |  |
| `854110` | semiconductors_and_sme | $685,843,022 (63 rec) | $511,985,823 (60 rec) | $424,763,903 (62 rec) | $552,602,128 (62 rec) | $2,175,194,876 |  |
| `854121` | semiconductors_and_sme | $177,933,281 (37 rec) | $125,874,885 (35 rec) | $103,664,984 (34 rec) | $136,028,678 (38 rec) | $543,501,828 |  |
| `854129` | semiconductors_and_sme | $1,304,132,957 (54 rec) | $1,211,639,720 (50 rec) | $1,100,763,849 (48 rec) | $1,543,331,500 (53 rec) | $5,159,868,026 |  |
| `854130` | semiconductors_and_sme | $106,904,285 (40 rec) | $85,497,490 (41 rec) | $64,349,139 (40 rec) | $74,252,095 (37 rec) | $331,003,009 |  |
| `854140` | semiconductors_and_sme | $5,604,065,096 (81 rec) | $8,427,935,905 (79 rec) | $10,470,590,319 (76 rec) | $9,556,549,366 (78 rec) | $34,059,140,686 |  |
| `854150` | semiconductors_and_sme | $430,418,593 (53 rec) | $403,242,568 (49 rec) | $403,359,507 (49 rec) | $829,974,738 (50 rec) | $2,066,995,406 |  |
| `854160` | semiconductors_and_sme | $362,545,656 (50 rec) | $265,866,519 (55 rec) | $329,123,113 (45 rec) | $346,757,782 (45 rec) | $1,304,293,070 |  |
| `854190` | semiconductors_and_sme | $230,875,248 (47 rec) | $285,382,882 (50 rec) | $318,897,767 (46 rec) | $396,415,132 (50 rec) | $1,231,571,029 |  |
| `854231` | semiconductors_and_sme | $21,619,335,521 (96 rec) | $21,831,882,288 (88 rec) | $21,403,723,805 (94 rec) | $27,551,319,937 (98 rec) | $92,406,261,551 |  |
| `854232` | semiconductors_and_sme | $3,030,260,106 (56 rec) | $1,801,292,465 (51 rec) | $1,691,681,037 (55 rec) | $2,228,543,926 (56 rec) | $8,751,777,534 |  |
| `854233` | semiconductors_and_sme | $1,304,179,439 (58 rec) | $1,152,050,710 (52 rec) | $804,841,188 (59 rec) | $650,843,464 (54 rec) | $3,911,914,801 |  |
| `854239` | semiconductors_and_sme | $8,528,902,976 (97 rec) | $8,028,539,941 (91 rec) | $7,731,843,327 (84 rec) | $10,504,769,130 (96 rec) | $34,794,055,374 |  |
| `854290` | semiconductors_and_sme | $313,481,641 (58 rec) | $271,280,583 (55 rec) | $277,947,686 (55 rec) | $315,776,546 (67 rec) | $1,178,486,456 |  |

No surviving code fell below the $1,000,000 cumulative-value floor.

## 4. PortWatch FeatureServer pagination

Chokepoint tested: **Strait of Malacca** (`chokepoint5`), the chokepoint PROJECT_BRIEF.md section 6 identifies as most relevant to both baskets.

- Pages fetched: 3 (rows per page: [1000, 1000, 806])
- Total daily rows retrieved: 2806
- Pagination confirmed working: yes. Layer `maxRecordCount` is 1000, and this chokepoint alone exceeds one page.

Columns returned:

- `ObjectId`
- `capacity`
- `capacity_cargo`
- `capacity_container`
- `capacity_dry_bulk`
- `capacity_general_cargo`
- `capacity_roro`
- `capacity_tanker`
- `date`
- `day`
- `month`
- `n_cargo`
- `n_container`
- `n_dry_bulk`
- `n_general_cargo`
- `n_roro`
- `n_tanker`
- `n_total`
- `portid`
- `portname`
- `year`
