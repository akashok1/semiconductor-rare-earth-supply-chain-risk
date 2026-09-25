-- Census import value by mode per HS6 code, country and year.
-- _YR fields are year-to-date cumulative, so December is the annual total;
-- never sum across months. Countries map to ISO3 through the Schedule C
-- crosswalk, with the manual overrides taking precedence. A country with no
-- ISO3 stays in as a flagged row: dropping it would shrink the exposure
-- denominator and hide unrouted value.

with december as (

    select
        i_commodity as hs6_code,
        hs_version,
        cast(left(time, 4) as integer) as year,
        cty_code,
        cty_name,
        gen_val_yr as gen_val,
        air_val_yr as air_val,
        ves_val_yr as ves_val,
        cnt_val_yr as cnt_val
    from {{ ref('stg_census_hs') }}
    where right(time, 2) = '12'

),

crosswalk as (

    select
        x.cty_code,
        -- An override row wins even when its iso3 is blank (Kosovo): blank
        -- is the decision, not a gap to fill from the generated crosswalk.
        case
            when o.cty_code is not null then nullif(o.iso3, '')
            else nullif(x.iso3, '')
        end as iso3
    from {{ ref('census_country_crosswalk') }} as x
    left join {{ ref('country_crosswalk_overrides') }} as o
        on o.cty_code = x.cty_code

)

select
    d.hs6_code,
    d.hs_version,
    d.year,
    d.cty_code,
    d.cty_name,
    c.iso3,
    c.iso3 is null as is_missing_iso3,
    d.gen_val,
    d.air_val,
    d.ves_val,
    d.cnt_val,
    -- Residual after vessel and air: land (truck, rail, pipeline) plus
    -- mail and other modes Census does not split out.
    d.gen_val - d.ves_val - d.air_val as land_val
from december as d
left join crosswalk as c
    on c.cty_code = d.cty_code
