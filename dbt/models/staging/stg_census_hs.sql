with source as (

    select * from {{ source('raw', 'census_hs_annual') }}

),

filtered as (

    select *
    from source
    -- summary_lvl = 'DET' alone is not enough: the grand-total sentinel row
    -- (cty_code = '-') is also tagged DET, and unfiltered it double counts
    -- against per-country rows (see CLAUDE.md, Census gotchas).
    where summary_lvl = 'DET'
      and cty_code != '-'

)

select
    i_commodity,
    cty_code,
    cty_name,
    summary_lvl,
    cast(gen_val_yr as numeric) as gen_val_yr,
    cast(air_val_yr as numeric) as air_val_yr,
    cast(ves_val_yr as numeric) as ves_val_yr,
    cast(cnt_val_yr as numeric) as cnt_val_yr,
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
