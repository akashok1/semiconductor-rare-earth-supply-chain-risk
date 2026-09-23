with source as (

    select * from {{ source('raw', 'portwatch_chokepoint_transits') }}

)

select
    -- portid holds a chokepoint id, not a port id (this source has 28
    -- chokepoints, not the full PortWatch port list).
    portid as chokepoint_id,
    portname,
    cast(date as date) as date,
    cast(n_container as numeric) as n_container,
    cast(n_dry_bulk as numeric) as n_dry_bulk,
    cast(n_general_cargo as numeric) as n_general_cargo,
    cast(n_roro as numeric) as n_roro,
    cast(n_tanker as numeric) as n_tanker,
    cast(n_cargo as numeric) as n_cargo,
    cast(n_total as numeric) as n_total,
    cast(capacity_container as numeric) as capacity_container,
    cast(capacity_dry_bulk as numeric) as capacity_dry_bulk,
    cast(capacity_general_cargo as numeric) as capacity_general_cargo,
    cast(capacity_roro as numeric) as capacity_roro,
    cast(capacity_tanker as numeric) as capacity_tanker,
    cast(capacity_cargo as numeric) as capacity_cargo,
    cast(capacity as numeric) as capacity,

    source_file,
    ingested_at

from source
-- Blackout dates (2022-05-12, 2023-02-14, 2024-01-09) are NOT excluded here.
-- Raw stays faithful; exclusion happens in the clean mart per FINDINGS.
