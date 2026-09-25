-- One 2x2 point per HS6 code, year, weighting and destination coast: the
-- single chokepoint with the highest modelled exposure at 200km (y-axis),
-- the same chokepoint's exposure at 100 and 300km (band), and the canonical
-- product's measured concentration (x-axis). Tie-break exposure desc, then
-- chokepoint_name, so the label is deterministic. Never a sum or union
-- across chokepoints. No 2x2 threshold columns: the lines are Tableau
-- parameters.

with exposure as (

    select * from {{ ref('fct_exposure') }}

),

ranked as (

    select
        *,
        row_number() over (
            partition by hs6_code, year, weighting, dest_coast
            order by exposure desc, chokepoint_name
        ) as rn
    from exposure
    where threshold_km = 200

),

max_chokepoint as (

    select * from ranked where rn = 1

),

band as (

    select
        hs6_code,
        year,
        weighting,
        dest_coast,
        chokepoint_id,
        max(exposure) filter (where threshold_km = 100) as exposure_100,
        max(exposure) filter (where threshold_km = 300) as exposure_300
    from exposure
    where threshold_km in (100, 300)
    group by 1, 2, 3, 4, 5

)

select
    m.basket,
    m.canonical_product_id,
    m.hs6_code,
    m.hs_version,
    m.year,
    m.weighting,
    m.dest_coast,
    -- No route crosses any chokepoint at 200km. Crossing is monotone in the
    -- threshold, so the 100km band is 0 too; the 300km band still reads the
    -- tie-break chokepoint and is shown, not zeroed.
    case when m.exposure > 0 then m.chokepoint_name else 'none' end
        as max_chokepoint,
    m.exposure as max_exposure_200,
    b.exposure_100,
    b.exposure_300,
    m.gen_val_total,
    m.cnt_val_total,
    m.vessel_coverage,
    m.unrouted_share,
    m.coast_residual,
    c.hhi,
    c.effective_suppliers,
    c.top1_partner_name,
    c.top1_share
from max_chokepoint as m
inner join band as b
    on b.hs6_code = m.hs6_code
    and b.year = m.year
    and b.weighting = m.weighting
    and b.dest_coast = m.dest_coast
    and b.chokepoint_id = m.chokepoint_id
left join {{ ref('fct_concentration') }} as c
    on c.canonical_product_id = m.canonical_product_id
    and c.year = m.year
