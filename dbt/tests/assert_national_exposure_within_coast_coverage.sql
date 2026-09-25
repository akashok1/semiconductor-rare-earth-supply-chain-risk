-- National exposure blends the three coasts by coast_share, which sums to
-- 1 - coast_residual, so it cannot exceed that fraction of vessel coverage.

select *
from {{ ref('fct_exposure') }}
where dest_coast = 'national'
  and exposure > vessel_coverage * (1 - coast_residual) + 0.000001
