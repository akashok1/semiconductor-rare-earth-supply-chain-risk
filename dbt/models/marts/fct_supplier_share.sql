-- US import value and share per supplier partner, per canonical product and
-- year (Comtrade, measured). Partner values are summed across every HS6
-- code of the canonical product first, then divided by the product-year
-- total, so a product spanning a vintage split is never an average of its
-- codes. World (partner 0) is excluded in staging.
--
-- Partner ISO3 and name come from Comtrade's own partner list, with manual
-- overrides taking precedence (490 "Other Asia, nes" is Taiwan).
-- is_aggregate_partner marks nes and area partners: they stay in as real
-- imports, with their value, and are flagged rather than dropped. "nes" is
-- matched as a whole word so Indonesia, Philippines, Polynesia and
-- Micronesia are not caught.

with imports as (

    select
        b.basket,
        b.canonical_product_id,
        c.ref_year as year,
        c.partner_code,
        c.import_value_usd
    from {{ ref('stg_comtrade') }} as c
    inner join {{ ref('hs_bridge') }} as b
        on b.hs6_code = c.hs6_code
        and b.hs_version = c.hs_version

),

product_partner as (

    select
        basket,
        canonical_product_id,
        year,
        partner_code,
        sum(import_value_usd) as import_value_usd
    from imports
    group by 1, 2, 3, 4

),

partners as (

    select
        p.partner_code,
        coalesce(o.iso3, p.partner_iso3) as partner_iso3,
        coalesce(o.partner_name, p.partner_desc) as partner_name,
        case
            when o.partner_code is not null then false
            else p.is_group or p.partner_desc ~* '\mnes\M'
        end as is_aggregate_partner
    from {{ ref('stg_comtrade_partners') }} as p
    left join {{ ref('comtrade_partner_overrides') }} as o
        on cast(o.partner_code as integer) = p.partner_code

)

select
    pp.basket,
    pp.canonical_product_id,
    pp.year,
    pp.partner_code,
    pa.partner_iso3,
    pa.partner_name,
    pa.is_aggregate_partner,
    pp.import_value_usd,
    pp.import_value_usd
        / nullif(sum(pp.import_value_usd) over (
            partition by pp.canonical_product_id, pp.year
        ), 0) as share,
    row_number() over (
        partition by pp.canonical_product_id, pp.year
        order by pp.import_value_usd desc, pp.partner_code
    ) as rank
from product_partner as pp
left join partners as pa
    on pa.partner_code = pp.partner_code
