-- Whether each origin port's route to each US coast crosses each
-- chokepoint, at every distance threshold in var('crossing_thresholds_km').
-- A route crosses when its minimum distance to the chokepoint point is
-- within the threshold. Chokepoints are points while straits are long, so
-- the threshold stands in for the strait's extent (see CLAUDE.md, Routing).

with thresholds as (

    select threshold_km
    from (
        values
        {%- for t in var('crossing_thresholds_km') %}
            ({{ t }}){{ "," if not loop.last }}
        {%- endfor %}
    ) as v (threshold_km)

)

select
    m.origin_portid,
    m.dest_coast,
    m.chokepoint_id,
    m.chokepoint_name,
    t.threshold_km,
    m.min_distance_km,
    m.min_distance_km <= t.threshold_km as crosses
from {{ ref('stg_routing_matrix') }} as m
cross join thresholds as t
