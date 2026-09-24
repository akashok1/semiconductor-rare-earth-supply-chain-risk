-- The h6_boundary_year var (dbt_project.yml) must equal the single distinct
-- non-null vintage_break_year in the hs_bridge seed. Staging models derive
-- hs_version from the var; the bridge derives its vintage break from the
-- source data. If they disagree, codes are tagged with the wrong vintage.
-- Returns a row (fails) on zero, several or a mismatched vintage_break_year.

with break_years as (

    select distinct cast(vintage_break_year as integer) as vintage_break_year
    from {{ ref('hs_bridge') }}
    where vintage_break_year is not null

)

select
    count(*) as distinct_break_years,
    min(vintage_break_year) as min_break_year,
    max(vintage_break_year) as max_break_year,
    {{ var('h6_boundary_year') }} as h6_boundary_year
from break_years
having count(*) != 1
    or min(vintage_break_year) != {{ var('h6_boundary_year') }}
