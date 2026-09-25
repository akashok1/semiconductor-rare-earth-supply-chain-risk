-- Every weighted port has an ok route to every US destination coast, and a
-- routing_matrix distance for every chokepoint on each of those routes. A
-- missing route or distance would silently shrink crossing_share.

with ports as (

    select distinct portid
    from {{ ref('int_port_weights') }}

),

expected as (

    select
        p.portid,
        d.coast as dest_coast
    from ports as p
    cross join {{ ref('us_destination_ports') }} as d

),

chokepoints as (

    select count(*) as n
    from {{ ref('stg_portwatch_chokepoints') }}

),

matrix as (

    select
        origin_portid,
        dest_coast,
        count(distinct chokepoint_id) as n
    from {{ ref('stg_routing_matrix') }}
    group by 1, 2

)

select
    e.portid,
    e.dest_coast,
    r.status,
    m.n as n_chokepoints
from expected as e
left join {{ ref('stg_routes') }} as r
    on r.origin_portid = e.portid
    and r.dest_coast = e.dest_coast
left join matrix as m
    on m.origin_portid = e.portid
    and m.dest_coast = e.dest_coast
cross join chokepoints as c
where r.status is distinct from 'ok'
   or m.n is distinct from c.n
