-- One 2x2 point per HS6 code, year, weighting and destination coast, with
-- two y-axis candidates, each the single chokepoint with the highest
-- modelled exposure at 200km plus the same chokepoint at 100 and 300km
-- (band):
--   flow_: over all 28 chokepoints (where the flow goes).
--   risk_: over the manual chokepoint_risk_set only (chokepoints with a
--          documented disruption).
-- Tie-break exposure desc, then chokepoint_name, so the label is
-- deterministic; 'none' when the top exposure is 0. Never a sum or union
-- across chokepoints. x-axis: the canonical product's measured
-- concentration. No 2x2 threshold columns: the lines are Tableau parameters.

with exposure as (

    select
        e.*,
        r.chokepoint_name is not null as in_risk_set
    from {{ ref('fct_exposure') }} as e
    left join {{ ref('chokepoint_risk_set') }} as r
        on r.chokepoint_name = e.chokepoint_name

),

-- Same chokepoint's exposure at every threshold, one row per chokepoint.
by_chokepoint as (

    select
        basket,
        canonical_product_id,
        hs6_code,
        hs_version,
        year,
        weighting,
        dest_coast,
        chokepoint_id,
        chokepoint_name,
        in_risk_set,
        gen_val_total,
        cnt_val_total,
        vessel_coverage,
        unrouted_share,
        coast_residual,
        max(exposure) filter (where threshold_km = 100) as exposure_100,
        max(exposure) filter (where threshold_km = 200) as exposure_200,
        max(exposure) filter (where threshold_km = 300) as exposure_300
    from exposure
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15

),

ranked as (

    select
        *,
        row_number() over (
            partition by hs6_code, year, weighting, dest_coast
            order by exposure_200 desc, chokepoint_name
        ) as flow_rn,
        row_number() over (
            partition by hs6_code, year, weighting, dest_coast, in_risk_set
            order by exposure_200 desc, chokepoint_name
        ) as risk_rn
    from by_chokepoint

),

flow as (

    select * from ranked where flow_rn = 1

),

risk as (

    select * from ranked where in_risk_set and risk_rn = 1

)

select
    f.basket,
    f.canonical_product_id,
    f.hs6_code,
    f.hs_version,
    f.year,
    f.weighting,
    f.dest_coast,
    -- 'none': no route crosses any chokepoint in the set at 200km. Crossing
    -- is monotone in the threshold, so the 100km band is 0 too; the 300km
    -- band still reads the tie-break chokepoint and is shown, not zeroed.
    case when f.exposure_200 > 0 then f.chokepoint_name else 'none' end
        as flow_max_chokepoint,
    f.exposure_200 as flow_max_exposure_200,
    f.exposure_100 as flow_exposure_100,
    f.exposure_300 as flow_exposure_300,
    case when r.exposure_200 > 0 then r.chokepoint_name else 'none' end
        as risk_max_chokepoint,
    r.exposure_200 as risk_max_exposure_200,
    r.exposure_100 as risk_exposure_100,
    r.exposure_300 as risk_exposure_300,
    f.gen_val_total,
    f.cnt_val_total,
    f.vessel_coverage,
    f.unrouted_share,
    f.coast_residual,
    c.hhi,
    c.effective_suppliers,
    c.top1_partner_name,
    c.top1_share
from flow as f
inner join risk as r
    on r.hs6_code = f.hs6_code
    and r.year = f.year
    and r.weighting = f.weighting
    and r.dest_coast = f.dest_coast
left join {{ ref('fct_concentration') }} as c
    on c.canonical_product_id = f.canonical_product_id
    and c.year = f.year
