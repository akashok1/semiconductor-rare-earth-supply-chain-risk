with source as (

    select * from {{ source('raw', 'portwatch_chokepoints') }}

)

select
    portid as chokepoint_id,
    portname,
    cast(lat as numeric) as lat,
    cast(lon as numeric) as lon,

    source_file,
    ingested_at

from source
