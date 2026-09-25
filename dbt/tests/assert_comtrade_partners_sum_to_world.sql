-- Comtrade completeness: per HS6 code and year, the partner rows in staging
-- sum to the raw World (partner 0) value within $1. Also fails where a
-- code-year has partner rows but no World row, or the reverse.

with world as (

    select
        cmd_code as hs6_code,
        cast(ref_year as integer) as year,
        cast(primary_value as numeric) as world_value
    from {{ source('raw', 'comtrade_imports') }}
    where cast(partner_code as integer) = 0

),

partners as (

    select
        hs6_code,
        ref_year as year,
        sum(import_value_usd) as partner_value
    from {{ ref('stg_comtrade') }}
    group by 1, 2

)

select
    coalesce(w.hs6_code, p.hs6_code) as hs6_code,
    coalesce(w.year, p.year) as year,
    w.world_value,
    p.partner_value
from world as w
full outer join partners as p
    on p.hs6_code = w.hs6_code
    and p.year = w.year
where w.world_value is null
    or p.partner_value is null
    or abs(w.world_value - p.partner_value) > 1
