-- Share of vessel import value landing on each US coast, per HS6 code and
-- year. porths_vessel carries no country, so these shares apply to every
-- partner of a code alike (disclosed limitation). Vessel value only:
-- general value by port is dominated by airports.
--
-- Port to coast: port_coast_overrides first, then the district coast map.
-- Ports missing from the Schedule D list take their district from the first
-- two digits of the port code (Census port codes are district + port).
-- Anything that is not west/east/gulf (interior, Great Lakes, land border,
-- non-geographic, unmapped) falls into coast_residual, never dropped.

with december as (

    select
        i_commodity as hs6_code,
        hs_version,
        cast(left(time, 4) as integer) as year,
        port,
        ves_val_yr as ves_val
    from {{ ref('stg_census_porths_vessel') }}
    where right(time, 2) = '12'

),

port_coast as (

    select
        d.hs6_code,
        d.hs_version,
        d.year,
        d.ves_val,
        coalesce(o.coast, m.coast, 'unmapped') as coast
    from december as d
    left join {{ ref('census_ports') }} as p
        on p.port_code = d.port
    left join {{ ref('district_coast_map') }} as m
        on m.district_code = coalesce(p.district_code, left(d.port, 2))
    left join {{ ref('port_coast_overrides') }} as o
        on o.port_code = d.port

),

code_year as (

    select
        hs6_code,
        hs_version,
        year,
        sum(ves_val) as total_ves_val
    from port_coast
    group by 1, 2, 3

),

coasts as (

    select coast
    from (values ('west'), ('east'), ('gulf')) as v (coast)

),

-- Every code-year gets all three coasts, so a coast with no vessel value
-- shows as 0 rather than a missing row.
coast_val as (

    select
        cy.hs6_code,
        cy.hs_version,
        cy.year,
        c.coast,
        cy.total_ves_val,
        coalesce(sum(pc.ves_val), 0) as coast_ves_val
    from code_year as cy
    cross join coasts as c
    left join port_coast as pc
        on pc.hs6_code = cy.hs6_code
        and pc.year = cy.year
        and pc.coast = c.coast
    group by 1, 2, 3, 4, 5

),

shares as (

    select
        *,
        coast_ves_val / nullif(total_ves_val, 0) as coast_share
    from coast_val

)

select
    hs6_code,
    hs_version,
    year,
    coast,
    coast_ves_val,
    total_ves_val,
    coast_share,
    1 - sum(coast_share) over (partition by hs6_code, year) as coast_residual
from shares
