-- Exposure routes only containerized value, and each country's crossing
-- share is at most 1, so exposure lies in [0, vessel_coverage].

select *
from {{ ref('fct_exposure') }}
where exposure < -0.000001
   or exposure > vessel_coverage + 0.000001
