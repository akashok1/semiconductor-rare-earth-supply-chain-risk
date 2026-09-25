with source as (

    select * from {{ source('raw', 'routes') }}

)

select
    origin_portid,
    origin_iso3,
    dest_coast,
    dest_portid,
    status,
    reason,
    cast(route_km as numeric) as route_km,
    cast(origin_snap_km as numeric) as origin_snap_km,
    cast(dest_snap_km as numeric) as dest_snap_km,

    source_file,
    ingested_at

from source
