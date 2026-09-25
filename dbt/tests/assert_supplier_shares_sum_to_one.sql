-- Partner shares sum to 1 per canonical product and year, within 0.0001.

select
    canonical_product_id,
    year,
    sum(share) as total
from {{ ref('fct_supplier_share') }}
group by 1, 2
having abs(coalesce(sum(share), 0) - 1) > 0.0001
