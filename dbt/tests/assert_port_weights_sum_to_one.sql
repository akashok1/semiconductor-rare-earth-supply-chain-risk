-- Port weights sum to 1 per partner country and weighting, within 0.001.

select
    iso3,
    weighting,
    sum(port_weight) as total
from {{ ref('int_port_weights') }}
group by 1, 2
having abs(coalesce(sum(port_weight), 0) - 1) > 0.001
