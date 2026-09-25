-- Weight of each foreign container port within its country, per partner
-- ISO3, in two weightings (long format):
--   export_share: share_country_maritime_export normalized over the
--                 country's ports with vessel_count_container > 0. Headline.
--   vessel_count: vessel_count_container normalized over the same ports.
--                 Sensitivity only.
-- Landlocked countries in landlocked_gateways with no container ports of
-- their own take their gateway country's ports and weights. Gateway rows
-- with a blank gateway_iso3 get no weights and stay unrouted.

with container_ports as (

    select
        portid,
        iso3,
        share_country_maritime_export,
        vessel_count_container
    from {{ ref('stg_portwatch_ports') }}
    where vessel_count_container > 0
      -- The US is the destination, never an origin; routing.py routes no
      -- US port.
      and iso3 != 'USA'

),

own_weights as (

    select
        iso3,
        portid,
        'export_share' as weighting,
        share_country_maritime_export
            / nullif(sum(share_country_maritime_export) over (partition by iso3), 0)
            as port_weight
    from container_ports

    union all

    select
        iso3,
        portid,
        'vessel_count' as weighting,
        vessel_count_container::numeric
            / sum(vessel_count_container) over (partition by iso3)
            as port_weight
    from container_ports

),

gateway_countries as (

    select
        g.iso3,
        g.gateway_iso3
    from {{ ref('landlocked_gateways') }} as g
    where nullif(g.gateway_iso3, '') is not null
      and not exists (
          select 1 from container_ports as p where p.iso3 = g.iso3
      )

)

select
    iso3,
    portid,
    weighting,
    port_weight,
    'own' as weight_source,
    cast(null as text) as gateway_iso3
from own_weights

union all

select
    g.iso3,
    w.portid,
    w.weighting,
    w.port_weight,
    'via_gateway' as weight_source,
    g.gateway_iso3
from gateway_countries as g
inner join own_weights as w
    on w.iso3 = g.gateway_iso3
