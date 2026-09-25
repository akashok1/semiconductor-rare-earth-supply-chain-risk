-- Share of a partner country's container port weight whose route to a US
-- coast crosses a chokepoint, per threshold and weighting:
--   crossing_share = sum over the country's ports of port_weight x crosses
-- No product or year: routing is static, product and year enter through
-- cnt_val and coast shares downstream. Never sum across chokepoints; one
-- route crosses several.

select
    w.iso3,
    c.dest_coast,
    c.chokepoint_id,
    c.chokepoint_name,
    c.threshold_km,
    w.weighting,
    w.weight_source,
    sum(w.port_weight * case when c.crosses then 1 else 0 end) as crossing_share,
    count(*) as n_ports
from {{ ref('int_port_weights') }} as w
inner join {{ ref('int_route_crossings') }} as c
    on c.origin_portid = w.portid
group by 1, 2, 3, 4, 5, 6, 7
