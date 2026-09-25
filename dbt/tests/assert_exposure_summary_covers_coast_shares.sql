-- Every HS6 code-year with coast shares has a 2x2 point for every
-- weighting and destination coast: none is silently dropped.

with expected as (

    select distinct s.hs6_code, s.year, w.weighting, k.dest_coast
    from {{ ref('int_coast_shares') }} as s
    cross join (values ('export_share'), ('vessel_count')) as w (weighting)
    cross join (values ('west'), ('east'), ('gulf'), ('national')) as k (dest_coast)

)

select e.*
from expected as e
left join {{ ref('fct_exposure_summary') }} as f
    on f.hs6_code = e.hs6_code
    and f.year = e.year
    and f.weighting = e.weighting
    and f.dest_coast = e.dest_coast
where f.hs6_code is null
