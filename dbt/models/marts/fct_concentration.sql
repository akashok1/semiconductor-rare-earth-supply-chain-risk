-- Supplier concentration per canonical product and year (Comtrade,
-- measured), from fct_supplier_share. HHI is on the 0-10,000 scale;
-- effective_suppliers = 10,000 / HHI. No 2x2 threshold column: the line is
-- a Tableau parameter.

with shares as (

    select * from {{ ref('fct_supplier_share') }}

),

-- Codes with nonzero value in the product-year. fct_supplier_share is
-- already summed across codes, so this one count reads staging.
codes as (

    select
        b.canonical_product_id,
        c.ref_year as year,
        count(distinct c.hs6_code) as n_codes
    from {{ ref('stg_comtrade') }} as c
    inner join {{ ref('hs_bridge') }} as b
        on b.hs6_code = c.hs6_code
        and b.hs_version = c.hs_version
    where c.import_value_usd > 0
    group by 1, 2

),

product_year as (

    select
        basket,
        canonical_product_id,
        year,
        sum(import_value_usd) as total_import_value_usd,
        10000 * sum(share * share) as hhi,
        sum(share) filter (where rank <= 3) as top3_share,
        count(*) filter (where import_value_usd > 0) as supplier_count
    from shares
    group by 1, 2, 3

)

select
    py.basket,
    py.canonical_product_id,
    py.year,
    py.total_import_value_usd,
    py.hhi,
    10000 / nullif(py.hhi, 0) as effective_suppliers,
    t.partner_name as top1_partner_name,
    t.partner_iso3 as top1_partner_iso3,
    t.share as top1_share,
    py.top3_share,
    py.supplier_count,
    coalesce(c.n_codes, 0) as n_codes
from product_year as py
left join shares as t
    on t.canonical_product_id = py.canonical_product_id
    and t.year = py.year
    and t.rank = 1
left join codes as c
    on c.canonical_product_id = py.canonical_product_id
    and c.year = py.year
