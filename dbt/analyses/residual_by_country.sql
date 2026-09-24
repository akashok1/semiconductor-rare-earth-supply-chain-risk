-- Mode residual (general value not carried by air or vessel) per origin
-- country, 2018-2025 cumulative across every bridge code. The residual is
-- land border trade plus mail and other modes; the verification phase
-- confirmed it against land border port share. This lists which countries
-- carry it, so land-dominant partners are visible before exposure excludes
-- their land value from routing (it stays in the denominator).
--
-- December rows only (Census _YR is year-to-date cumulative).
-- stg_census_hs already keeps SUMMARY_LVL = 'DET' and drops the '-' sentinel.

with december as (

    select
        cty_code,
        cty_name,
        gen_val_yr,
        air_val_yr,
        ves_val_yr
    from {{ ref('stg_census_hs') }}
    where right(time, 2) = '12'

),

per_country as (

    select
        cty_code,
        cty_name,
        sum(gen_val_yr) as gen_val,
        sum(gen_val_yr - air_val_yr - ves_val_yr) as residual_val
    from december
    group by cty_code, cty_name

)

select
    cty_code,
    cty_name,
    gen_val,
    residual_val,
    residual_val / nullif(gen_val, 0) as residual_share_of_country,
    residual_val / nullif(sum(residual_val) over (), 0) as share_of_total_residual
from per_country
order by residual_val desc
