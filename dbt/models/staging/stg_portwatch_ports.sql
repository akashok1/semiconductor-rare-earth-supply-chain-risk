with source as (

    select * from {{ source('raw', 'portwatch_ports') }}

)

select
    portid,
    portname,
    country,
    iso3,
    continent,
    fullname,
    locode,
    cast(lat as numeric) as lat,
    cast(lon as numeric) as lon,
    cast(vessel_count_total as integer) as vessel_count_total,
    cast(vessel_count_container as integer) as vessel_count_container,
    cast(vessel_count_dry_bulk as integer) as vessel_count_dry_bulk,
    cast(vessel_count_general_cargo as integer) as vessel_count_general_cargo,
    cast(vessel_count_roro as integer) as vessel_count_roro,
    cast(vessel_count_tanker as integer) as vessel_count_tanker,
    industry_top1,
    industry_top2,
    industry_top3,
    -- Percent (0-100) of the country's maritime trade through this port.
    cast(share_country_maritime_import as numeric) as share_country_maritime_import,
    cast(share_country_maritime_export as numeric) as share_country_maritime_export,

    source_file,
    ingested_at

from source
