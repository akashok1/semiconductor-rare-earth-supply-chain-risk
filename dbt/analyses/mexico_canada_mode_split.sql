-- Mode split of Mexico and Canada imports per HS6 code and year.
-- Reproduces the verification finding that Mexico (95.5%) and Canada (74.8%)
-- are land dominant, which is why exposure routes each country's own
-- containerized vessel value rather than a code-level vessel share.
--
-- December rows only: Census _YR fields are year-to-date cumulative, so
-- December is the annual total and summing months inflates ~6.2x.
-- stg_census_hs already keeps SUMMARY_LVL = 'DET' and drops the '-' sentinel.
-- land_other is the residual gen - air - ves (land border trade, plus mail
-- and other modes).

with december as (

    select
        i_commodity as hs6_code,
        cast(left(time, 4) as integer) as year,
        cty_code,
        cty_name,
        gen_val_yr,
        air_val_yr,
        ves_val_yr,
        cnt_val_yr
    from {{ ref('stg_census_hs') }}
    where right(time, 2) = '12'
      and cty_code in ('1220', '2010')  -- Canada, Mexico

),

per_code_year as (

    select
        cty_name,
        hs6_code,
        year,
        gen_val_yr,
        air_val_yr / nullif(gen_val_yr, 0) as air_share,
        ves_val_yr / nullif(gen_val_yr, 0) as vessel_share,
        cnt_val_yr / nullif(gen_val_yr, 0) as container_vessel_share,
        (gen_val_yr - air_val_yr - ves_val_yr) / nullif(gen_val_yr, 0) as land_other_share
    from december

),

per_country as (

    -- 2018-2025 cumulative, value weighted, the basis of the headline figures.
    select
        cty_name,
        'all' as hs6_code,
        null::integer as year,
        sum(gen_val_yr) as gen_val_yr,
        sum(air_val_yr) / nullif(sum(gen_val_yr), 0) as air_share,
        sum(ves_val_yr) / nullif(sum(gen_val_yr), 0) as vessel_share,
        sum(cnt_val_yr) / nullif(sum(gen_val_yr), 0) as container_vessel_share,
        sum(gen_val_yr - air_val_yr - ves_val_yr) / nullif(sum(gen_val_yr), 0) as land_other_share
    from december
    group by cty_name

)

select * from per_country
union all
select * from per_code_year
order by cty_name, hs6_code, year
