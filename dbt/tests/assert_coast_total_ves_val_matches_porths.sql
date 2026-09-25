-- int_coast_shares.total_ves_val must equal the December vessel value in
-- stg_census_porths_vessel for each code-year, within 1 dollar. Catches
-- ports dropped or double counted by the port to coast joins.

with expected as (

    select
        i_commodity as hs6_code,
        cast(left(time, 4) as integer) as year,
        sum(ves_val_yr) as ves_val
    from {{ ref('stg_census_porths_vessel') }}
    where right(time, 2) = '12'
    group by 1, 2

),

actual as (

    select distinct
        hs6_code,
        year,
        total_ves_val
    from {{ ref('int_coast_shares') }}

)

select
    coalesce(e.hs6_code, a.hs6_code) as hs6_code,
    coalesce(e.year, a.year) as year,
    e.ves_val,
    a.total_ves_val
from expected as e
full outer join actual as a
    on a.hs6_code = e.hs6_code
    and a.year = e.year
where abs(coalesce(e.ves_val, 0) - coalesce(a.total_ves_val, 0)) > 1
   or e.hs6_code is null
   or a.hs6_code is null
