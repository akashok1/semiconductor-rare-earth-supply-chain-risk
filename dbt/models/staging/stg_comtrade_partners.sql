with source as (

    select * from {{ source('raw', 'comtrade_partners') }}

)

select
    cast(partner_code as integer) as partner_code,
    -- Some names and pseudo-ISO3 codes carry trailing spaces in the source.
    trim(partner_desc) as partner_desc,
    trim(partner_note) as partner_note,
    trim(partner_iso2) as partner_iso2,
    -- Aggregates carry pseudo-codes here (W00 World, S19 Other Asia nes,
    -- _X Areas nes), not ISO 3166-1.
    trim(partner_iso3) as partner_iso3,
    cast(entry_effective_date as date) as entry_effective_date,
    cast(entry_expired_date as date) as entry_expired_date,
    cast(is_group as boolean) as is_group,

    source_file,
    ingested_at

from source
