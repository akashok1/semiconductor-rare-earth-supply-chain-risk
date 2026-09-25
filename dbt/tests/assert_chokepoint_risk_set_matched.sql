-- Every chokepoint in the manual risk set names a PortWatch chokepoint
-- exactly; a typo would silently drop it from the risk_ columns.

select r.*
from {{ ref('chokepoint_risk_set') }} as r
left join {{ ref('stg_portwatch_chokepoints') }} as c
    on c.portname = r.chokepoint_name
where c.chokepoint_id is null
