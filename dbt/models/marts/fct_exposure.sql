-- Modelled chokepoint exposure per HS6 code, year, chokepoint, threshold,
-- weighting and US destination coast (Census plus computed routes):
--   exposure_k = sum over countries of cnt_val x crossing_share(k)
--                / gen_val_total
--   national   = sum over coasts k of coast_share(k) x exposure_k
-- gen_val_total covers every country and mode, including countries with no
-- ISO3 or no port weights: they add 0 to the numerator but stay in the
-- denominator, so unrouted value is never silently dropped. Air and land
-- value are never routed. Never sum exposure across chokepoints; one route
-- crosses several.

with countries as (

    select * from {{ ref('int_census_country_mode') }}

),

code_year as (

    select
        c.hs6_code,
        c.hs_version,
        c.year,
        sum(c.gen_val) as gen_val_total,
        sum(c.cnt_val) as cnt_val_total,
        -- Countries without port weights: no ISO3, or an ISO3 with no own
        -- or gateway ports (blank-gateway territories).
        coalesce(sum(c.cnt_val) filter (
            where c.iso3 is null
               or c.iso3 not in (select iso3 from {{ ref('int_port_weights') }})
        ), 0) as cnt_val_unrouted
    from countries as c
    group by 1, 2, 3

),

coast_residual as (

    select distinct
        hs6_code,
        year,
        coast_residual
    from {{ ref('int_coast_shares') }}

),

chokepoints as (

    select distinct
        chokepoint_id,
        chokepoint_name
    from {{ ref('int_country_crossing_share') }}

),

thresholds as (

    select threshold_km
    from (
        values
        {%- for t in var('crossing_thresholds_km') %}
            ({{ t }}){{ "," if not loop.last }}
        {%- endfor %}
    ) as v (threshold_km)

),

weightings as (

    select weighting
    from (values ('export_share'), ('vessel_count')) as v (weighting)

),

coasts as (

    select dest_coast
    from (values ('west'), ('east'), ('gulf')) as v (dest_coast)

),

-- Full grid, so a chokepoint no partner's route crosses shows as 0 rather
-- than a missing row.
grid as (

    select
        cy.hs6_code,
        cy.hs_version,
        cy.year,
        k.dest_coast,
        cp.chokepoint_id,
        cp.chokepoint_name,
        t.threshold_km,
        w.weighting
    from code_year as cy
    cross join coasts as k
    cross join chokepoints as cp
    cross join thresholds as t
    cross join weightings as w

),

crossed_value as (

    select
        c.hs6_code,
        c.year,
        s.dest_coast,
        s.chokepoint_id,
        s.threshold_km,
        s.weighting,
        sum(c.cnt_val * s.crossing_share) as crossed_cnt_val
    from countries as c
    inner join {{ ref('int_country_crossing_share') }} as s
        on s.iso3 = c.iso3
    group by 1, 2, 3, 4, 5, 6

),

single_coast as (

    select
        g.*,
        coalesce(v.crossed_cnt_val, 0) / cy.gen_val_total as exposure
    from grid as g
    inner join code_year as cy
        on cy.hs6_code = g.hs6_code
        and cy.year = g.year
    left join crossed_value as v
        on v.hs6_code = g.hs6_code
        and v.year = g.year
        and v.dest_coast = g.dest_coast
        and v.chokepoint_id = g.chokepoint_id
        and v.threshold_km = g.threshold_km
        and v.weighting = g.weighting

),

national as (

    select
        e.hs6_code,
        e.hs_version,
        e.year,
        'national' as dest_coast,
        e.chokepoint_id,
        e.chokepoint_name,
        e.threshold_km,
        e.weighting,
        sum(s.coast_share * e.exposure) as exposure
    from single_coast as e
    inner join {{ ref('int_coast_shares') }} as s
        on s.hs6_code = e.hs6_code
        and s.year = e.year
        and s.coast = e.dest_coast
    group by 1, 2, 3, 4, 5, 6, 7, 8

),

exposure as (

    select * from single_coast
    union all
    select * from national

)

select
    b.basket,
    b.canonical_product_id,
    e.hs6_code,
    e.hs_version,
    e.year,
    e.chokepoint_id,
    e.chokepoint_name,
    e.threshold_km,
    e.weighting,
    e.dest_coast,
    e.exposure,
    cy.gen_val_total,
    cy.cnt_val_total,
    cy.cnt_val_total / cy.gen_val_total as vessel_coverage,
    cy.cnt_val_unrouted / nullif(cy.cnt_val_total, 0) as unrouted_share,
    -- Vessel value landing outside the three coasts only discounts the
    -- national blend; a single-coast row assumes all of it lands there.
    case when e.dest_coast = 'national' then r.coast_residual else 0 end
        as coast_residual
from exposure as e
inner join code_year as cy
    on cy.hs6_code = e.hs6_code
    and cy.year = e.year
inner join coast_residual as r
    on r.hs6_code = e.hs6_code
    and r.year = e.year
inner join {{ ref('hs_bridge') }} as b
    on b.hs6_code = e.hs6_code
    and b.hs_version = e.hs_version
