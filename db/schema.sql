-- Raw landing DDL for import-concentration-risk.
--
-- Applied to Postgres before dbt runs. Idempotent: safe to re-run in full
-- against an existing database.
--
-- All source columns land as text; casting happens in dbt staging
-- (dbt/models/staging/, prefix stg_). Every table also carries source_file,
-- ingested_at, and a payload jsonb column holding the full source row, so
-- staging can always fall back to the untouched original if a named column
-- turns out to be wrong or incomplete.

CREATE SCHEMA IF NOT EXISTS raw;

-- ============================================================
-- comtrade_imports
-- UN Comtrade bilateral trade data (annual US imports by partner and HS6).
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.comtrade_imports (
    type_code                   text,
    freq_code                   text,
    ref_period_id                text,
    ref_year                     text,
    ref_month                    text,
    period                       text,
    reporter_code                text,
    reporter_iso                 text,
    reporter_desc                text,
    flow_code                    text,
    flow_desc                    text,
    partner_code                 text,
    partner_iso                  text,
    partner_desc                 text,
    partner2_code                text,
    partner2_iso                 text,
    partner2_desc                text,
    classification_code          text,
    classification_search_code   text,
    is_original_classification   text,
    cmd_code                     text,
    cmd_desc                     text,
    aggr_level                   text,
    is_leaf                       text,
    customs_code                 text,
    customs_desc                 text,
    mos_code                     text,
    mot_code                     text,
    mot_desc                     text,
    qty_unit_code                text,
    qty_unit_abbr                text,
    qty                          text,
    is_qty_estimated             text,
    alt_qty_unit_code            text,
    alt_qty_unit_abbr            text,
    alt_qty                      text,
    is_alt_qty_estimated         text,
    net_wgt                      text,
    is_net_wgt_estimated         text,
    gross_wgt                    text,
    is_gross_wgt_estimated       text,
    cifvalue                     text,
    fobvalue                     text,
    primary_value                text,
    legacy_estimation_flag       text,
    is_reported                  text,
    is_aggregate                 text,
    hs_version                   text NOT NULL,
    source_file                  text NOT NULL,
    ingested_at                  timestamptz NOT NULL DEFAULT now(),
    payload                      jsonb NOT NULL
);

COMMENT ON TABLE raw.comtrade_imports IS
    'UN Comtrade bilateral trade data, loaded from data/raw/comtrade_final_C_A_HS_*.json';
COMMENT ON COLUMN raw.comtrade_imports.hs_version IS
    'Classification vintage, sourced from classificationCode (e.g. H5). Not a source column itself -- carried separately so every row knows its vintage across HS revisions without staging having to re-derive it from classification_code.';

CREATE INDEX IF NOT EXISTS ix_comtrade_imports_cmd_code ON raw.comtrade_imports (cmd_code);
CREATE INDEX IF NOT EXISTS ix_comtrade_imports_partner_code ON raw.comtrade_imports (partner_code);
CREATE INDEX IF NOT EXISTS ix_comtrade_imports_ref_year ON raw.comtrade_imports (ref_year);
CREATE INDEX IF NOT EXISTS ix_comtrade_imports_hs_version ON raw.comtrade_imports (hs_version);

-- ============================================================
-- census_hs_annual
-- US Census international trade, HS6 x country annual import value with
-- air/vessel/containerized-vessel splits.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.census_hs_annual (
    i_commodity        text,
    cty_code           text,
    cty_name           text,
    summary_lvl        text,
    gen_val_yr         text,
    air_val_yr         text,
    ves_val_yr         text,
    cnt_val_yr         text,
    comm_lvl           text,
    i_commodity_echo   text,
    time               text,
    source_file        text NOT NULL,
    ingested_at         timestamptz NOT NULL DEFAULT now(),
    payload             jsonb NOT NULL
);

COMMENT ON TABLE raw.census_hs_annual IS
    'US Census international trade, HS6 x country annual import value with mode-of-transport splits, loaded from data/raw/census_hs_annual_*.json';
COMMENT ON COLUMN raw.census_hs_annual.i_commodity_echo IS
    'Second I_COMMODITY column from the source header. This is the filter parameter echoed back by the Census API, not a distinct field.';
COMMENT ON COLUMN raw.census_hs_annual.payload IS
    'Full source row, built positionally from the header and row arrays. Do not build it with dict(zip(header, row)) -- the duplicate I_COMMODITY key collapses in a dict and silently drops the echoed filter value.';

CREATE INDEX IF NOT EXISTS ix_census_hs_annual_i_commodity ON raw.census_hs_annual (i_commodity);
CREATE INDEX IF NOT EXISTS ix_census_hs_annual_cty_code ON raw.census_hs_annual (cty_code);
CREATE INDEX IF NOT EXISTS ix_census_hs_annual_summary_lvl ON raw.census_hs_annual (summary_lvl);
CREATE INDEX IF NOT EXISTS ix_census_hs_annual_time ON raw.census_hs_annual (time);

-- ============================================================
-- census_porths_annual
-- US Census international trade, HS6 x port-of-entry annual general import
-- value. No vessel split -- superseded by census_porths_vessel below.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.census_porths_annual (
    i_commodity        text,
    port               text,
    port_name          text,
    summary_lvl        text,
    gen_val_yr         text,
    comm_lvl           text,
    i_commodity_echo   text,
    time               text,
    source_file        text NOT NULL,
    ingested_at         timestamptz NOT NULL DEFAULT now(),
    payload             jsonb NOT NULL
);

COMMENT ON TABLE raw.census_porths_annual IS
    'US Census international trade, HS6 x port-of-entry annual general import value, loaded from data/raw/census_porths_annual_*.json. Superseded by raw.census_porths_vessel -- this table has no vessel value column, so it cannot support coast shares. Not to be used for coast shares.';
COMMENT ON COLUMN raw.census_porths_annual.i_commodity_echo IS
    'Second I_COMMODITY column from the source header. This is the filter parameter echoed back by the Census API, not a distinct field.';
COMMENT ON COLUMN raw.census_porths_annual.payload IS
    'Full source row, built positionally from the header and row arrays. Do not build it with dict(zip(header, row)) -- the duplicate I_COMMODITY key collapses in a dict and silently drops the echoed filter value.';

CREATE INDEX IF NOT EXISTS ix_census_porths_annual_i_commodity ON raw.census_porths_annual (i_commodity);
CREATE INDEX IF NOT EXISTS ix_census_porths_annual_port ON raw.census_porths_annual (port);
CREATE INDEX IF NOT EXISTS ix_census_porths_annual_summary_lvl ON raw.census_porths_annual (summary_lvl);
CREATE INDEX IF NOT EXISTS ix_census_porths_annual_time ON raw.census_porths_annual (time);

-- ============================================================
-- census_porths_vessel
-- US Census international trade, HS6 x port-of-entry annual import value
-- with vessel value. Source of coast shares for the exposure formula.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.census_porths_vessel (
    i_commodity        text,
    port               text,
    port_name          text,
    summary_lvl        text,
    gen_val_yr         text,
    ves_val_yr         text,
    comm_lvl           text,
    i_commodity_echo   text,
    time               text,
    source_file        text NOT NULL,
    ingested_at         timestamptz NOT NULL DEFAULT now(),
    payload             jsonb NOT NULL
);

COMMENT ON TABLE raw.census_porths_vessel IS
    'US Census international trade, HS6 x port-of-entry annual import value with vessel value, loaded from data/raw/census_porths_vessel_*.json';
COMMENT ON COLUMN raw.census_porths_vessel.i_commodity_echo IS
    'Second I_COMMODITY column from the source header. This is the filter parameter echoed back by the Census API, not a distinct field.';
COMMENT ON COLUMN raw.census_porths_vessel.payload IS
    'Full source row, built positionally from the header and row arrays. Do not build it with dict(zip(header, row)) -- the duplicate I_COMMODITY key collapses in a dict and silently drops the echoed filter value.';

CREATE INDEX IF NOT EXISTS ix_census_porths_vessel_i_commodity ON raw.census_porths_vessel (i_commodity);
CREATE INDEX IF NOT EXISTS ix_census_porths_vessel_port ON raw.census_porths_vessel (port);
CREATE INDEX IF NOT EXISTS ix_census_porths_vessel_summary_lvl ON raw.census_porths_vessel (summary_lvl);
CREATE INDEX IF NOT EXISTS ix_census_porths_vessel_time ON raw.census_porths_vessel (time);

-- ============================================================
-- portwatch_chokepoint_transits
-- IMF PortWatch daily vessel transit counts and vessel-type/capacity mix
-- per chokepoint.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.portwatch_chokepoint_transits (
    portid                    text,
    portname                  text,
    date                      text,
    n_container               text,
    n_dry_bulk                text,
    n_general_cargo           text,
    n_roro                    text,
    n_tanker                  text,
    n_cargo                   text,
    n_total                   text,
    capacity_container        text,
    capacity_dry_bulk         text,
    capacity_general_cargo    text,
    capacity_roro             text,
    capacity_tanker           text,
    capacity_cargo            text,
    capacity                  text,
    source_file               text NOT NULL,
    ingested_at               timestamptz NOT NULL DEFAULT now(),
    payload                   jsonb NOT NULL
);

COMMENT ON TABLE raw.portwatch_chokepoint_transits IS
    'IMF PortWatch daily vessel transit counts and vessel-type/capacity mix per chokepoint, loaded from data/raw/portwatch_full_offset*.json';

CREATE INDEX IF NOT EXISTS ix_portwatch_chokepoint_transits_portid ON raw.portwatch_chokepoint_transits (portid);
CREATE INDEX IF NOT EXISTS ix_portwatch_chokepoint_transits_date ON raw.portwatch_chokepoint_transits (date);

-- ============================================================
-- portwatch_chokepoints
-- IMF PortWatch chokepoint point coordinates (28 chokepoints).
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.portwatch_chokepoints (
    portid        text,
    portname      text,
    lat           text,
    lon           text,
    source_file   text NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    payload       jsonb NOT NULL
);

COMMENT ON TABLE raw.portwatch_chokepoints IS
    'IMF PortWatch chokepoint point coordinates, loaded from data/raw/portwatch_chokepoints_geometry.json';

CREATE INDEX IF NOT EXISTS ix_portwatch_chokepoints_portid ON raw.portwatch_chokepoints (portid);
