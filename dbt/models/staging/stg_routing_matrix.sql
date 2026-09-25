with source as (

    select * from {{ source('raw', 'routing_matrix') }}

)

select
    origin_portid,
    dest_coast,
    dest_portid,
    chokepoint_id,
    chokepoint_name,
    cast(min_distance_km as numeric) as min_distance_km,

    source_file,
    ingested_at

from source
