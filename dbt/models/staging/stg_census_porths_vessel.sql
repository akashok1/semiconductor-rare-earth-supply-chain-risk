with source as (

    select * from {{ source('raw', 'census_porths_vessel') }}

),

filtered as (

    select *
    from source
    -- Same DET/sentinel trap as stg_census_hs, but the sentinel here is the
    -- port dimension's grand total (port = '-'), not the country dimension's.
    where summary_lvl = 'DET'
      and port != '-'

)

select
    i_commodity,
    port,
    port_name,
    summary_lvl,
    -- gen_val_yr is deliberately not carried forward: port distribution
    -- computed on general value returns airports, per the documented trap.
    -- Only vessel value belongs in this model.
    cast(ves_val_yr as numeric) as ves_val_yr,
    comm_lvl,
    time,
    case
        when cast(left(time, 4) as integer) < {{ var('h6_boundary_year') }}
            then 'H5'
        else 'H6'
    end as hs_version,

    source_file,
    ingested_at

from filtered
