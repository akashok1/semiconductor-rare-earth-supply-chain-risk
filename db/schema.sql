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

-- ============================================================
-- portwatch_ports
-- IMF PortWatch ports database: every port with ISO3, LOCODE, vessel counts
-- by type and the port's share of its country's maritime trade. Source of
-- port weights (share_country_maritime_export) for the exposure formula.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.portwatch_ports (
    portid                          text,
    portname                        text,
    country                         text,
    iso3                            text,
    continent                       text,
    fullname                        text,
    lat                             text,
    lon                             text,
    vessel_count_total              text,
    vessel_count_container          text,
    vessel_count_dry_bulk           text,
    vessel_count_general_cargo      text,
    vessel_count_roro               text,
    vessel_count_tanker             text,
    industry_top1                   text,
    industry_top2                   text,
    industry_top3                   text,
    share_country_maritime_import   text,
    share_country_maritime_export   text,
    locode                          text,
    pageid                          text,
    countrynoaccents                text,
    objectid                        text,
    source_file                     text NOT NULL,
    ingested_at                     timestamptz NOT NULL DEFAULT now(),
    payload                         jsonb NOT NULL
);

COMMENT ON TABLE raw.portwatch_ports IS
    'IMF PortWatch ports database, loaded from data/raw/portwatch_ports_database_offset*.json';
COMMENT ON COLUMN raw.portwatch_ports.payload IS
    'Full ArcGIS feature: attributes and geometry (point, outSR 4326).';

CREATE INDEX IF NOT EXISTS ix_portwatch_ports_portid ON raw.portwatch_ports (portid);
CREATE INDEX IF NOT EXISTS ix_portwatch_ports_iso3 ON raw.portwatch_ports (iso3);

-- ============================================================
-- portwatch_disruptions
-- IMF PortWatch disruptions database: disruption events (storms,
-- earthquakes, floods and similar) with dates, alert level and affected
-- ports. Ingested for a future disruption case study; no mart reads it.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.portwatch_disruptions (
    eventid              text,
    eventtype            text,
    eventname            text,
    htmlname             text,
    htmldescription      text,
    alertlevel           text,
    country              text,
    fromdate             text,
    year                 text,
    todate               text,
    severitytext         text,
    lat                  text,
    long                 text,
    editdate             text,
    affectedports        text,
    n_affectedports      text,
    affectedpopulation   text,
    pageid               text,
    objectid             text,
    shape_area           text,
    shape_length         text,
    source_file          text NOT NULL,
    ingested_at          timestamptz NOT NULL DEFAULT now(),
    payload              jsonb NOT NULL
);

COMMENT ON TABLE raw.portwatch_disruptions IS
    'IMF PortWatch disruptions database, loaded from data/raw/portwatch_disruptions_offset*.json';
COMMENT ON COLUMN raw.portwatch_disruptions.payload IS
    'Full ArcGIS feature: attributes and geometry (event area polygon rings, outSR 4326). The polygon is only in payload.';

CREATE INDEX IF NOT EXISTS ix_portwatch_disruptions_eventid ON raw.portwatch_disruptions (eventid);

-- ============================================================
-- routes
-- One row per origin port x US destination coast, from ingest/routing.py
-- (searoute over every PortWatch port with container traffic). status and
-- reason record routes that could not be computed.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.routes (
    origin_portid    text,
    origin_iso3      text,
    dest_coast       text,
    dest_portid      text,
    status           text,
    reason           text,
    route_km         text,
    origin_snap_km   text,
    dest_snap_km     text,
    source_file      text NOT NULL,
    ingested_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.routes IS
    'Computed sea routes, loaded from data/reference/generated/routes.csv (written by ingest/routing.py). CSV source: no payload column; every source column is named.';

CREATE INDEX IF NOT EXISTS ix_routes_origin_portid ON raw.routes (origin_portid);

-- ============================================================
-- routing_matrix
-- Minimum distance from each computed route to each chokepoint, from
-- ingest/routing.py. crosses = min_distance_km <= threshold is computed in
-- dbt, not here.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.routing_matrix (
    origin_portid     text,
    dest_coast        text,
    dest_portid       text,
    chokepoint_id     text,
    chokepoint_name   text,
    min_distance_km   text,
    source_file       text NOT NULL,
    ingested_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.routing_matrix IS
    'Route to chokepoint minimum distances, loaded from data/reference/generated/routing_matrix.csv (written by ingest/routing.py). CSV source: no payload column; every source column is named.';

CREATE INDEX IF NOT EXISTS ix_routing_matrix_origin_portid ON raw.routing_matrix (origin_portid);
CREATE INDEX IF NOT EXISTS ix_routing_matrix_chokepoint_id ON raw.routing_matrix (chokepoint_id);
