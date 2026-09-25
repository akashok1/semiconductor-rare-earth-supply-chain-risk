-- crossing_share is a weighted share of one country's ports, so it lies in
-- [0, 1] (small tolerance for numeric rounding).

select *
from {{ ref('int_country_crossing_share') }}
where crossing_share is null
   or crossing_share < -0.000001
   or crossing_share > 1.000001
